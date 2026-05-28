from decimal import Decimal
from zoneinfo import ZoneInfo
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from django.db.models import Q, Count, Sum, Value, DecimalField, Max
from django.db.models.functions import TruncDate, Coalesce
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from django.utils import timezone
from django.contrib import messages
from django.core.mail import EmailMessage

from ..models import Venta, RetiroCaja, MovimientoStock, Ingreso, Articulo, BajaStock

from .utilidades import (
    _get_local_activo,
    _saldo_caja_local,
    money,
    money_or_dash,
    safe,
    ensure_space,
    ar_dt,
    fmt_ar_dt,
    fmt_ar_date,
)

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _draw_centered_header(c, w, h, title, subtitle_lines):
    top = h - 42

    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(w / 2, top, title)

    y = top - 18
    c.setFont("Helvetica", 9)
    for line in subtitle_lines:
        c.drawCentredString(w / 2, y, line)
        y -= 12

    y -= 2
    c.setLineWidth(0.8)
    c.line(40, y, w - 40, y)

    return y - 18


def _draw_sales_summary_block(c, w, y, ventas_count, unidades, subtotal, descuentos, total, costo, resultado):
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Resumen de ventas")
    y -= 18

    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Comprobantes: {ventas_count}")
    y -= 14
    c.drawString(40, y, f"Unidades: {unidades}")
    y -= 16

    c.drawString(40, y, f"Subtotal: {money(subtotal)}")
    y -= 14
    c.drawString(40, y, f"Descuentos: {money(descuentos)}")
    y -= 14
    c.drawString(40, y, f"Costo total: {money_or_dash(costo)}")
    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Total vendido: {money(total)}")
    y -= 14
    c.drawString(40, y, f"Ganancia: {money_or_dash(resultado)}")
    y -= 30

    return y


def _draw_sale_title(c, w, y, venta):
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Venta {fmt_ar_dt(venta.fecha)}")
    y -= 14

    usuario_txt = ""
    if hasattr(venta.usuario, "get_full_name"):
        usuario_txt = venta.usuario.get_full_name().strip()
    if not usuario_txt:
        usuario_txt = venta.usuario.username

    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Usuario: {usuario_txt}   Método de pago: {venta.get_metodo_de_pago_display()}")
    y -= 10

    c.setLineWidth(0.6)
    c.line(40, y, w - 40, y)
    y -= 14

    return y


def _draw_sale_table_header(c, w, y):
    cols = [
        (40,  "SKU", "L"),
        (270, "Código", "L"),
        (355, "Cant.", "R"),
        (430, "Precio u.", "R"),
        (485, "Desc.", "R"),
        (w - 40, "Total", "R"),
    ]

    c.setFont("Helvetica-Bold", 9)
    for x, txt, align in cols:
        if align == "R":
            c.drawRightString(x, y, txt)
        else:
            c.drawString(x, y, txt)

    y -= 14
    c.setFont("Helvetica", 9)
    return y

def _draw_sale_totals(c, w, y, venta, costo_total, ganancia_total):
    c.setLineWidth(0.6)
    c.line(315, y, w - 40, y)
    y -= 18

    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(
        w - 40,
        y,
        f"Subtotal: {money(venta.subtotal)}   Desc.: {money(venta.total_descuento)}   Costo: {money_or_dash(costo_total)}"
    )
    y -= 20

    c.drawRightString(
        w - 40,
        y,
        f"Total: {money(venta.total)}   Ganancia: {money_or_dash(ganancia_total)}"
    )
    y -= 30

    return y

def _estimate_sale_block_height(venta):
    items = list(venta.items.all())
    h = 34   # título + usuario + línea
    h += 16  # table header
    for it in items:
        h += 12
        descuento_u = Decimal(getattr(it, "descuento_unitario", 0) or 0)
        promo_obj = getattr(it, "promocion", None)
        promo_nombre = getattr(promo_obj, "nombre", "") if promo_obj else ""
        if descuento_u > 0 and promo_nombre:
            h += 10
    h += 6
    h += 34  # totales
    h += 18  # aire entre comprobantes
    return h

def _render_ventas_pdf(
    request,
    local,
    ventas_qs,
    include_caja=False,
    caja_fecha=None,
    caja_usuario=None,
):
    ventas = list(
        ventas_qs
        .select_related("usuario", "local")
        .prefetch_related("items", "items__producto", "items__producto__marca", "items__promocion")
        .order_by("-fecha", "-venta_id")
    )

    if not ventas:
        return HttpResponse("No hay ventas para exportar.", status=400)

    venta_ids = [v.venta_id for v in ventas]

    ventas_agg = (
        Venta.objects
        .filter(venta_id__in=venta_ids)
        .aggregate(
            ventas=Count("venta_id"),
            subtotal_bruto=Coalesce(Sum("subtotal"), Value(0, output_field=DecimalField())),
            descuento_total=Coalesce(Sum("total_descuento"), Value(0, output_field=DecimalField())),
            venta_total=Coalesce(Sum("total"), Value(0, output_field=DecimalField())),
        )
    )

    ms_global_agg = (
        MovimientoStock.objects
        .filter(venta_id__in=venta_ids, tipo=MovimientoStock.Tipo.VENTA)
        .aggregate(
            unidades=Count("movimiento_id"),
            costo_total=Sum("costo_unitario"),
            profit_total=Sum("profit_unitario"),
            costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
            ganancias_desconocidas=Count("movimiento_id", filter=Q(profit_unitario__isnull=True)),
        )
    )

    fechas = [ar_dt(v.fecha) for v in ventas if v.fecha]
    min_fecha = min(fechas)
    max_fecha = max(fechas)

    if min_fecha.date() == max_fecha.date():
        fecha_line = f"Fecha: {fmt_ar_date(min_fecha)}"
    else:
        fecha_line = f"Rango: {fmt_ar_date(min_fecha)} a {fmt_ar_date(max_fecha)}"

    usuarios = sorted({
        (v.usuario.get_full_name().strip() if hasattr(v.usuario, "get_full_name") else "") or v.usuario.username
        for v in ventas
    })
    usuarios_txt = ", ".join(usuarios) if usuarios else "-"

    caja_rows = []
    caja_total = Decimal("0.00")

    if include_caja and caja_fecha:
        caja_qs = (
            RetiroCaja.objects
            .filter(local=local, fecha=caja_fecha)
            .select_related("usuario")
            .order_by("-creado_en")
        )

        if caja_usuario and not request.user.is_staff:
            caja_qs = caja_qs.filter(usuario=caja_usuario)

        caja_rows = list(caja_qs)

        caja_total = (
            caja_qs.aggregate(
                total=Coalesce(Sum("monto"), Value(0, output_field=DecimalField()))
            )["total"] or Decimal("0.00")
        )

    resp = HttpResponse(content_type="application/pdf")
    if len(ventas) == 1 and not include_caja:
        filename = f'venta_{ventas[0].venta_id}.pdf'
    elif include_caja:
        filename = "resumen_dia.pdf"
    else:
        filename = "reporte_ventas.pdf"
    resp["Content-Disposition"] = f'inline; filename="{filename}"'

    c = canvas.Canvas(resp, pagesize=A4)
    w, h = A4

    def header():
        title = "Resumen del Día" if include_caja else "Reporte de Ventas - FreeDonna"
        return _draw_centered_header(
            c, w, h,
            title=title,
            subtitle_lines=[
                f"Local: {local.nombre}",
                fecha_line,
                f"Usuarios: {safe(usuarios_txt, 110)}",
                f"Generado: {timezone.now().astimezone(AR_TZ).strftime('%Y-%m-%d %H:%M')}",
            ]
        )

    y = header()

    if len(ventas) > 1:
        y = ensure_space(c, w, h, y, min_y=150, repeat_header_fn=header)
        y = _draw_sales_summary_block(
            c, w, y,
            ventas_count=ventas_agg["ventas"] or 0,
            unidades=ms_global_agg["unidades"] or 0,
            subtotal=ventas_agg["subtotal_bruto"],
            descuentos=ventas_agg["descuento_total"],
            total=ventas_agg["venta_total"],
            costo=None if ms_global_agg["costos_desconocidos"] else (ms_global_agg["costo_total"] or Decimal("0.00")),
            resultado=None if ms_global_agg["ganancias_desconocidas"] else (ms_global_agg["profit_total"] or Decimal("0.00")),
        )

    for venta in ventas:
        estimated_height = _estimate_sale_block_height(venta)

        if y < max(120, 60 + estimated_height):
            c.showPage()
            y = header()

        venta_ms_agg = (
            MovimientoStock.objects
            .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
            .aggregate(
                costo_total=Sum("costo_unitario"),
                profit_total=Sum("profit_unitario"),
                costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
                ganancias_desconocidas=Count("movimiento_id", filter=Q(profit_unitario__isnull=True)),
            )
        )

        y = _draw_sale_title(c, w, y, venta)
        y = _draw_sale_table_header(c, w, y)

        items = list(venta.items.all().order_by("item_id"))

        for it in items:
            if y < 95:
                c.showPage()
                y = header()
                y = _draw_sale_title(c, w, y, venta)
                y = _draw_sale_table_header(c, w, y)

            sku_base = safe(getattr(it, "sku", ""), 20)
            talle = safe(getattr(it, "talle", ""), 8)
            color = safe(getattr(it, "color", ""), 12)
            sku = safe(f"{sku_base} {color} {talle}".strip(), 34)

            barcode = safe(getattr(it, "barcode", ""), 24)
            qty = int(getattr(it, "cantidad", 1) or 1)

            precio_u = Decimal(getattr(it, "precio_unitario", 0) or 0)
            descuento_u = Decimal(getattr(it, "descuento_unitario", 0) or 0)
            total_linea = Decimal(getattr(it, "total_linea", 0) or 0)
            descuento_total = descuento_u * qty

            c.setFont("Helvetica", 9)
            c.drawString(40, y, sku)
            c.drawString(270, y, barcode)
            c.drawRightString(355, y, str(qty))
            c.drawRightString(430, y, money(precio_u))
            c.drawRightString(485, y, money(descuento_total))
            c.drawRightString(w - 40, y, money(total_linea))
            y -= 12

            promo_obj = getattr(it, "promocion", None)
            promo_nombre = getattr(promo_obj, "nombre", "") if promo_obj else ""
            if descuento_u > 0 and promo_nombre:
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(40, y, safe(f"Promo aplicada: {promo_nombre}", 100))
                y -= 11

        y -= 6
        y = _draw_sale_totals(
            c, w, y,
            venta=venta,
            costo_total=None if venta_ms_agg["costos_desconocidos"] else (venta_ms_agg["costo_total"] or Decimal("0.00")),
            ganancia_total=None if venta_ms_agg["ganancias_desconocidas"] else (venta_ms_agg["profit_total"] or Decimal("0.00")),
        )

    if include_caja:
        y = ensure_space(c, w, h, y, min_y=140, repeat_header_fn=header)

        c.setStrokeColor(colors.HexColor("#D9DEE7"))
        c.line(40, y, w - 40, y)
        y -= 18

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#1F2A44"))
        c.drawString(40, y, "Gastos de caja del día")
        y -= 16

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#5B657A"))
        c.drawString(40, y, f"Cantidad de movimientos: {len(caja_rows)}")
        c.drawRightString(w - 40, y, f"Total gastos: {money(caja_total)}")
        y -= 18

        if caja_rows:
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(colors.HexColor("#1F2A44"))
            c.drawString(40, y, "Hora")
            c.drawString(95, y, "Usuario")
            c.drawRightString(w - 40, y, "Monto")
            y -= 10

            c.setStrokeColor(colors.HexColor("#D9DEE7"))
            c.line(40, y, w - 40, y)
            y -= 14

            for mov in caja_rows:
                y = ensure_space(c, w, h, y, min_y=90, repeat_header_fn=header)

                fecha_mov = getattr(mov, "creado_en", None) or getattr(mov, "fecha_hora", None)
                hora = ar_dt(fecha_mov).strftime("%H:%M") if fecha_mov else "--:--"

                usuario_txt = "-"
                if getattr(mov, "usuario", None):
                    usuario_txt = (
                        mov.usuario.get_full_name().strip()
                        if hasattr(mov.usuario, "get_full_name") and mov.usuario.get_full_name().strip()
                        else mov.usuario.username
                    )
                monto = getattr(mov, "monto", Decimal("0.00")) or Decimal("0.00")
                motivo = getattr(mov, "motivo", "") or ""
                nota = getattr(mov, "nota", "") or ""

                # fila principal
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.black)
                c.drawString(40, y, hora)
                c.drawString(95, y, safe(usuario_txt, 28))
                c.drawString(230, y, safe(motivo, 25))   # 👈 motivo
                c.drawRightString(w - 40, y, money(monto))
                y -= 12

                
                if nota:
                    c.setFont("Helvetica-Oblique", 8)
                    c.setFillColor(colors.HexColor("#5B657A"))
                    c.drawString(95, y, safe(nota, 80))
                    y -= 11
        else:
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#5B657A"))
            c.drawString(40, y, "No se registraron gastos de caja en el día.")
            y -= 14

    c.save()
    return resp

def venta_pdf(request, venta_id: int):
    local = _get_local_activo(request)

    venta = get_object_or_404(
        Venta.objects.select_related("local", "usuario"),
        venta_id=venta_id
    )

    if local and venta.local_id != local.local_id:
        return HttpResponse("No autorizado para este local.", status=403)

    ventas_qs = Venta.objects.filter(venta_id=venta.venta_id, local=venta.local)
    return _render_ventas_pdf(request, venta.local, ventas_qs)

def movimiento_pdf(request):
    if not request.user.is_staff:
        return HttpResponse("No autorizado.", status=403)

    local = _get_local_activo(request)
    if not local:
        return HttpResponse("No hay local activo.", status=400)

    mode = (request.GET.get("mode") or "doc").strip().lower()
    tipo = (request.GET.get("tipo") or "all").strip().upper()
    q = (request.GET.get("q") or "").strip()
    desde = (request.GET.get("from") or "").strip()
    hasta = (request.GET.get("to") or "").strip()

    base = (
        MovimientoStock.objects
        .filter(local=local)
        .select_related("producto", "venta", "ingreso", "articulo", "usuario")
    )

    if tipo in ["IN", "OUT", "ADJ", "TRF", "BAJ", "RET"]:
        base = base.filter(tipo=tipo)

    if q:
        base = base.filter(
            Q(barcode__icontains=q) |
            Q(sku__icontains=q) |
            Q(producto__nombre__icontains=q) |
            Q(producto__marca__nombre__icontains=q)
        )

    if desde:
        base = base.filter(fecha__date__gte=desde)
    if hasta:
        base = base.filter(fecha__date__lte=hasta)

    is_sales_report = (mode == "doc" and tipo in ["OUT", "VENTA"])
    if is_sales_report:
        venta_ids = list(
            base.exclude(venta_id=None)
                .values_list("venta_id", flat=True)
                .distinct()
        )

        ventas_qs = Venta.objects.filter(venta_id__in=venta_ids, local=local)
        return _render_ventas_pdf(request, local, ventas_qs)

    is_ingresos_report = (mode == "doc" and tipo in ["IN", "INGRESO"])
    if is_ingresos_report:
        ingreso_ids = list(
            base.exclude(ingreso_id=None)
                .values_list("ingreso_id", flat=True)
                .distinct()
        )

        ingresos_qs = Ingreso.objects.filter(ingreso_id__in=ingreso_ids, local=local)
        return _render_ingresos_pdf(request, local, ingresos_qs)

    if mode == "unit":
        rows = list(base.order_by("-fecha", "-movimiento_id")[:1500])
    elif mode == "day":
        rows = list(
            base.annotate(dia=TruncDate("fecha"))
                .values("dia")
                .annotate(
                    movimientos=Count("movimiento_id"),
                    unidades=Sum("cantidad"),
                    costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                    venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                    profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                )
                .order_by("-dia")
        )
    elif mode == "variant":
        rows = list(
            base.values("barcode", "sku", "talle", "color", "producto__nombre", "producto__marca__nombre")
                .annotate(
                    movimientos=Count("movimiento_id"),
                    unidades=Sum("cantidad"),
                    costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                    venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                    profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                    last_fecha=Max("fecha"),
                )
                .order_by("barcode", "talle", "color")
        )
    else:
        rows = list(
            base.values("tipo", "venta_id", "ingreso_id")
                .annotate(
                    fecha=Max("fecha"),
                    items=Count("movimiento_id"),
                    costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                    venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                    profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                )
                .order_by("-fecha")
        )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="movimientos.pdf"'
    c = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    y = _draw_centered_header(
        c, w, h,
        title=f"Movimientos de Stock - {local.nombre}",
        subtitle_lines=[
            f"Modo: {mode}  |  Tipo: {tipo}",
            f"Rango: {desde or '-'} a {hasta or '-'}",
            f"Generado: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
        ]
    )

    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Render de movimientos general pendiente / conservar lógica actual.")
    c.save()
    return response

def pos_resumen_dia_pdf(request):
    local = _get_local_activo(request)
    if not local:
        return HttpResponse("No hay local activo.", status=400)

    hoy = timezone.localdate()

    ventas_qs = (
        Venta.objects
        .filter(
            usuario=request.user,
            local=local,
            estado=Venta.Estado.CERRADA,
            fecha__date=hoy,
        )
        .order_by("-fecha", "-venta_id")
    )

    return _render_ventas_pdf(
        request,
        local,
        ventas_qs,
        include_caja=True,
        caja_fecha=hoy,
        caja_usuario=request.user,
    )
    
def _get_resumen_dia_base(request):
    local = _get_local_activo(request)
    if not local:
        return None, None, None

    hoy = timezone.localdate()

    ventas_qs = (
        Venta.objects
        .select_related("usuario", "local")
        .filter(
            usuario=request.user,
            local=local,
            estado=Venta.Estado.CERRADA,
            fecha__date=hoy,
        )
        .order_by("-fecha", "-venta_id")
    )

    return local, hoy, ventas_qs


def _build_pos_resumen_dia_context(request):
    local, hoy, ventas_qs = _get_resumen_dia_base(request)
    if not local:
        return None

    ventas = list(ventas_qs)
    efectivo=_saldo_caja_local(local)
    ventas_agg = ventas_qs.aggregate(
        cantidad_ventas=Coalesce(Count("venta_id"), 0),
        total_vendido=Coalesce(Sum("total"), Value(0, output_field=DecimalField())),
    )

    movimientos_caja_qs = (
        RetiroCaja.objects
        .select_related("usuario", "local")
        .filter(
            usuario=request.user,
            local=local,
            fecha=hoy,
        )
        .order_by("-fecha", "-retiro_id")
    )

    movimientos_caja = list(movimientos_caja_qs)

    total_mov_caja = movimientos_caja_qs.aggregate(
        total=Coalesce(Sum("monto"), Value(0, output_field=DecimalField()))
    )["total"]

    resumen = {
        "cantidad_ventas": ventas_agg["cantidad_ventas"] or 0,
        "total_vendido": ventas_agg["total_vendido"] or 0,
        "caja_efectivo": efectivo,
        "neto_caja": total_mov_caja or 0,
    }
    email = "joaquindores@gmail.com"
    return {
        "local": local,
        "hoy": hoy,
        "ventas": ventas,
        "movimientos_caja": movimientos_caja,
        "resumen": resumen,
        "email_destino": email,
    }


def _generar_pdf_resumen_dia_response(request):
    local, hoy, ventas_qs = _get_resumen_dia_base(request)
    if not local:
        return HttpResponse("No hay local activo.", status=400)

    return _render_ventas_pdf(
        request,
        local,
        ventas_qs,
        include_caja=True,
        caja_fecha=hoy,
        caja_usuario=request.user,
    )


@login_required
def pos_resumen_dia_view(request):
    ctx = _build_pos_resumen_dia_context(request)
    if ctx is None:
        messages.error(request, "No hay local activo.")
        return redirect("inventory:pos")

    return render(request, "inventory/pos/export_caja.html", ctx)


@login_required
def pos_resumen_dia_enviar_view(request):
    if request.method != "POST":
        return redirect("inventory:pos_resumen_dia")

    ctx = _build_pos_resumen_dia_context(request)
    if ctx is None:
        messages.error(request, "No hay local activo.")
        return redirect("inventory:pos")

    local = ctx["local"]
    email_destino = ctx["email_destino"]

    if not email_destino:
        messages.error(request, "Este local no tiene configurado un email de destino.")
        return redirect("inventory:pos_resumen_dia")

    try:
        pdf_response = _generar_pdf_resumen_dia_response(request)
        if pdf_response.status_code != 200:
            messages.error(request, "No se pudo generar el PDF del resumen.")
            return redirect("inventory:pos_resumen_dia")

        pdf_bytes = pdf_response.content

        fecha_txt = timezone.localtime().strftime("%d-%m-%Y")
        nombre_local = getattr(local, "nombre", "local")

        email = EmailMessage(
            subject=f"Resumen del día - {nombre_local} - {fecha_txt}",
            body=(
                f"Se adjunta el resumen del día.\n\n"
                f"Local: {nombre_local}\n"
                f"Empleado: {request.user.get_username()}\n"
                f"Fecha: {fecha_txt}\n"
            ),
            to=[email_destino],
        )

        email.attach(
            f"resumen_dia_{nombre_local}_{fecha_txt}.pdf",
            pdf_bytes,
            "application/pdf"
        )
        email.send(fail_silently=False)

        messages.success(request, f"Resumen enviado a {email_destino}.")
    except Exception as e:
        messages.error(request, f"No se pudo enviar el resumen: {e}")

    return redirect("inventory:pos_resumen_dia")


def _draw_ingresos_header(c, w, h, title, subtitle_lines):
    top = h - 42

    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(w / 2, top, title)

    y = top - 18
    c.setFont("Helvetica", 9)
    for line in subtitle_lines:
        c.drawCentredString(w / 2, y, line)
        y -= 12

    y -= 2
    c.setLineWidth(0.8)
    c.line(40, y, w - 40, y)

    return y - 22
def _draw_ingresos_summary_block(c, y, ingresos_count, unidades, costo_total):
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Resumen del reporte")
    y -= 18

    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Comprobantes: {ingresos_count}")
    y -= 12
    c.drawString(40, y, f"Unidades: {unidades}")
    y -= 12
    c.drawString(40, y, f"Costo total: {money_or_dash(costo_total)}")
    y -= 28

    return y

def _draw_ingreso_title(c, w, y, ingreso):
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Ingreso {fmt_ar_dt(ingreso.fecha)}")
    y -= 14

    usuario_txt = ""
    if hasattr(ingreso.usuario, "get_full_name"):
        usuario_txt = ingreso.usuario.get_full_name().strip()
    if not usuario_txt:
        usuario_txt = ingreso.usuario.username

    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Usuario: {usuario_txt}")
    y -= 12

    if ingreso.referencia:
        c.drawString(40, y, f"Referencia: {safe(ingreso.referencia, 90)}")
        y -= 12

    if ingreso.nota:
        c.drawString(40, y, f"Nota: {safe(ingreso.nota, 95)}")
        y -= 12

    c.setLineWidth(0.6)
    c.line(40, y, w - 40, y)
    y -= 14

    return y

def _draw_ingreso_table_header(c, w, y):
    cols = [
        (40,  "SKU", "L"),
        (280, "Código", "L"),
        (430, "Cant.", "R"),
        (505, "Costo u.", "R"),
        (w - 40, "Total", "R"),
    ]

    c.setFont("Helvetica-Bold", 9)
    for x, txt, align in cols:
        if align == "R":
            c.drawRightString(x, y, txt)
        else:
            c.drawString(x, y, txt)

    y -= 14
    c.setFont("Helvetica", 9)
    return y

def _draw_ingreso_totals(c, w, y, ingreso, costo_total, unidades):
    c.setLineWidth(0.6)
    c.line(360, y, w - 40, y)
    y -= 16

    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(w - 40, y, f"Costo total: {money_or_dash(costo_total)}")
    y -= 14

    c.drawRightString(w - 40, y, f"Unidades: {unidades}")
    y -= 28

    return y

def _estimate_ingreso_block_height(ingreso):
    items = list(ingreso.items.all())
    h = 52  # título + usuario + línea base

    if ingreso.referencia:
        h += 12
    if ingreso.nota:
        h += 12

    h += 16  # header tabla
    h += 12 * len(items)
    h += 42  # cierre
    h += 18  # aire entre comprobantes

    return h

def _render_ingresos_pdf(request, local, ingresos_qs):
    ingresos = list(
        ingresos_qs
        .select_related("usuario", "local")
        .prefetch_related("items")
        .order_by("-fecha", "-ingreso_id")
    )

    if not ingresos:
        return HttpResponse("No hay ingresos para exportar.", status=400)

    ingreso_ids = [i.ingreso_id for i in ingresos]

    ingresos_agg = (
        Ingreso.objects
        .filter(ingreso_id__in=ingreso_ids)
        .aggregate(
            ingresos=Count("ingreso_id"),
        )
    )

    ms_global_agg = (
        MovimientoStock.objects
        .filter(ingreso_id__in=ingreso_ids, tipo=MovimientoStock.Tipo.INGRESO)
        .aggregate(
            unidades=Coalesce(Sum("cantidad"), Value(0)),
            costo_total=Sum("costo_unitario"),
            costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
        )
    )

    fechas = [ar_dt(i.fecha) for i in ingresos if i.fecha]
    min_fecha = min(fechas)
    max_fecha = max(fechas)

    if min_fecha.date() == max_fecha.date():
        fecha_line = f"Fecha: {fmt_ar_date(min_fecha)}"
    else:
        fecha_line = f"Rango: {fmt_ar_date(min_fecha)} a {fmt_ar_date(max_fecha)}"

    usuarios = sorted({
        (i.usuario.get_full_name().strip() if hasattr(i.usuario, "get_full_name") else "") or i.usuario.username
        for i in ingresos
    })
    usuarios_txt = ", ".join(usuarios) if usuarios else "-"

    resp = HttpResponse(content_type="application/pdf")
    if len(ingresos) == 1:
        filename = f'ingreso_{ingresos[0].ingreso_id}.pdf'
    else:
        filename = "reporte_ingresos.pdf"
    resp["Content-Disposition"] = f'inline; filename="{filename}"'

    c = canvas.Canvas(resp, pagesize=A4)
    w, h = A4

    def header():
        return _draw_ingresos_header(
            c, w, h,
            title="Reporte de Ingresos - FreeDonna",
            subtitle_lines=[
                f"Local: {local.nombre}",
                fecha_line,
                f"Usuarios: {safe(usuarios_txt, 110)}",
                f"Generado: {timezone.now().astimezone(AR_TZ).strftime('%Y-%m-%d %H:%M')}",
            ]
        )

    y = header()

    if len(ingresos) > 1:
        y = ensure_space(c, w, h, y, min_y=150, repeat_header_fn=header)
        y = _draw_ingresos_summary_block(
            c, y,
            ingresos_count=ingresos_agg["ingresos"] or 0,
            unidades=ms_global_agg["unidades"] or 0,
            costo_total=None if ms_global_agg["costos_desconocidos"] else (ms_global_agg["costo_total"] or Decimal("0.00")),
        )

    for ingreso in ingresos:
        estimated_height = _estimate_ingreso_block_height(ingreso)

        if y < max(120, 60 + estimated_height):
            c.showPage()
            y = header()

        ingreso_ms_agg = (
            MovimientoStock.objects
            .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
            .aggregate(
                unidades=Count("movimiento_id"),
                costo_total=Sum("costo_unitario"),
                costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
            )
        )

        y = _draw_ingreso_title(c, w, y, ingreso)
        y = _draw_ingreso_table_header(c, w, y)

        items = list(ingreso.items.all().order_by("item_id"))

        for it in items:
            if y < 95:
                c.showPage()
                y = header()
                y = _draw_ingreso_title(c, w, y, ingreso)
                y = _draw_ingreso_table_header(c, w, y)

            sku = safe(getattr(it, "sku", ""), 30)
            barcode = safe(getattr(it, "barcode", ""), 24)
            qty = int(getattr(it, "cantidad", 1) or 1)
            costo_u = Decimal(getattr(it, "costo_unitario", 0) or 0)
            total_linea = (costo_u * qty) if costo_u else Decimal("0.00")

            c.setFont("Helvetica", 9)
            c.drawString(40, y, sku)
            c.drawString(280, y, barcode)
            c.drawRightString(430, y, str(qty))
            c.drawRightString(505, y, money(costo_u))
            c.drawRightString(w - 40, y, money(total_linea))
            y -= 12

        y -= 6
        y = _draw_ingreso_totals(
            c, w, y,
            ingreso=ingreso,
            costo_total=None if ingreso_ms_agg["costos_desconocidos"] else (ingreso_ms_agg["costo_total"] or Decimal("0.00")),
            unidades=ingreso_ms_agg["unidades"] or 0,
        )

    c.save()
    return resp

def ingreso_pdf(request, ingreso_id: int):
    local = _get_local_activo(request)

    ingreso = get_object_or_404(
        Ingreso.objects.select_related("local", "usuario"),
        ingreso_id=ingreso_id
    )

    if local and ingreso.local_id != local.local_id:
        return HttpResponse("No autorizado para este local.", status=403)

    ingresos_qs = Ingreso.objects.filter(ingreso_id=ingreso.ingreso_id, local=ingreso.local)
    return _render_ingresos_pdf(request, ingreso.local, ingresos_qs)
