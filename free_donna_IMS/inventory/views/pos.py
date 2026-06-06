from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render, HttpResponse
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, DeleteView, TemplateView, FormView
from django.db.models import Q, Count, ExpressionWrapper, Sum, Max, Value, CharField, F, Case, When
from django.db.models.fields import DecimalField, IntegerField
from django.shortcuts import redirect
from httpcore import request
from sqlalchemy import Cast
from ..models import BajaStock, Ingreso, IngresoItem, Local, Marca, MovimientoStock, Producto, Articulo, ProductoBulkAdjust, ProductoBulkAdjustItem, Promocion, RetiroCaja, Transferencia, TransferenciaItem, Venta, VentaItem, VentaArticulo
from ..forms import ArticuloEditForm, ArticuloImportXlsxForm, CheckoutForm, ProductoImportXlsxForm, PromocionForm, TransferirArticuloForm, UserLoginForm, UserRegisterForm, ArticuloCreateForm, ArticuloImportXlsxForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.edit import FormView
from django.db import transaction
from django.contrib import messages
from datetime import datetime as Datetime, time, timedelta, timezone, datetime
from django.db.models.functions import TruncDate, Coalesce, TruncMinute, Concat
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from django.utils import timezone
from openpyxl import load_workbook
from django.core.mail import EmailMessage

from .utilidades import (
    _get_cart, _save_cart, _cart_totals, _get_local_activo, _saldo_caja_local,
    _get_devolucion, _save_devolucion, _clear_devolucion, _articulo_ya_devuelto,
    _get_credito_devolucion
)
# Lógica de promociones centralizada en promociones.py (la versión correcta).
from .promociones import get_mejor_promocion_para_producto


class POSView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos.html"

    def get(self, request):
        cart = _get_cart(request.session)
        local = _get_local_activo(request)
        dev = _get_devolucion(request.session)

        barcodes = [it["barcode"] for it in cart.values()]
        stock_map = {}
        if barcodes and local:
            rows = (
                Articulo.objects
                .filter(local=local, barcode__in=barcodes, estado=Articulo.Estado.DISPONIBLE)
                .values("barcode")
                .annotate(disponibles=Count("articulo_id"))
            )
            stock_map = {r["barcode"]: r["disponibles"] for r in rows}

        totals = _cart_totals(cart)

        credito_total = Decimal("0.00")
        diferencia_cobrar = totals["subtotal_final"]

        if dev and dev.get("articulo_devuelto_id"):
            credito_total = Decimal(dev.get("credito_total", "0") or "0")
            diferencia_cobrar = totals["subtotal_final"] - credito_total
            if diferencia_cobrar < 0:
                diferencia_cobrar = Decimal("0.00")

        hoy = timezone.localdate()
        ventas_qs = (
            Venta.objects
            .filter(
                usuario=request.user,
                local=local if local else None,
                estado=Venta.Estado.CERRADA,
                fecha__date=hoy,
            )
            .order_by("-venta_id")
        )
        agg = ventas_qs.aggregate(
            ventas_hoy_count=Count("venta_id"),
            ventas_hoy_total=Coalesce(Sum("total"), Decimal("0.00")),
        )
        ventas_hoy = ventas_qs.values("venta_id", "fecha", "metodo_de_pago", "total")[:50]
        total_en_efectivo = _saldo_caja_local(local)

        devolucion_q = (request.GET.get("dq") or "").strip()
        vendidos = []
        if dev is not None and devolucion_q:
            # Buscar artículos vendidos que coincidan con la búsqueda
            articulos_vendidos = (
                Articulo.objects
                .select_related("product_id", "product_id__marca", "local")
                .filter(
                    Q(estado=Articulo.Estado.VENDIDO),
                    Q(barcode__icontains=devolucion_q)
                    | Q(sku__icontains=devolucion_q)
                    | Q(product_id__nombre__icontains=devolucion_q)
                )
                .order_by("-articulo_id")[:100]
            )
            
            # Obtener los precios de venta de cada artículo
            articulos_ids = [a.articulo_id for a in articulos_vendidos]
            venta_articulos = VentaArticulo.objects.filter(
                articulo_id__in=articulos_ids
            ).select_related('venta')
            
            # Mapear articulo_id -> venta_id
            articulo_venta_map = {va.articulo_id: va.venta_id for va in venta_articulos}
            
            # Obtener los items de venta para saber el precio unitario
            venta_ids = list(set(articulo_venta_map.values()))
            venta_items = VentaItem.objects.filter(venta_id__in=venta_ids)
            
            # Mapear (venta_id, barcode, talle, color) -> precio_unitario
            precio_map = {}
            for vi in venta_items:
                key = (vi.venta_id, vi.barcode, vi.talle, vi.color)
                precio_map[key] = vi.precio_unitario
            
            # Agrupar artículos por (producto, barcode, talle, color, marca, precio)
            grupos = {}
            for a in articulos_vendidos:
                venta_id = articulo_venta_map.get(a.articulo_id)
                precio = precio_map.get((venta_id, a.barcode, a.talle, a.color), Decimal("0.00"))
                
                key = (
                    a.product_id.nombre,
                    a.barcode,
                    a.sku,
                    a.talle,
                    a.color,
                    a.product_id.marca.nombre if a.product_id.marca else None,
                    precio
                )
                
                if key not in grupos:
                    grupos[key] = {
                        'articulos': [],
                        'nombre': a.product_id.nombre,
                        'barcode': a.barcode,
                        'sku': a.sku,
                        'talle': a.talle,
                        'color': a.color,
                        'marca': a.product_id.marca.nombre if a.product_id.marca else None,
                        'precio': precio,
                        'cantidad': 0
                    }
                
                grupos[key]['articulos'].append(a.articulo_id)
                grupos[key]['cantidad'] += 1
            
            # Convertir a lista y tomar los primeros 30 grupos
            vendidos = sorted(grupos.values(), key=lambda x: -x['cantidad'])[:30]

        return render(request, self.template_name, {
            "cart": cart,
            "stock_map": stock_map,
            "subtotal_base": totals["subtotal_base"],
            "subtotal": totals["subtotal_final"],
            "total": totals["subtotal_final"],
            "total_descuento": totals["total_descuento"],

            "devolucion_data": dev,
            "devolucion_activa": bool(dev),
            "credito_total": credito_total,
            "diferencia_cobrar": diferencia_cobrar,
            "devolucion_q": devolucion_q,
            "vendidos": vendidos,

            "total_en_efectivo": total_en_efectivo,
            "local_activo": local,
            "hoy": hoy,
            "ventas_hoy": list(ventas_hoy),
            "ventas_hoy_count": agg["ventas_hoy_count"] or 0,
            "ventas_hoy_total": agg["ventas_hoy_total"] or Decimal("0.00"),
        })  

class POSCajaView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos_caja.html"
    def get(self, request):
        local = _get_local_activo(request)
        hoy = timezone.localdate()

        saldo_actual = _saldo_caja_local(local)

        movimientos_hoy = (
            RetiroCaja.objects
            .filter(local=local, fecha=hoy)
            .select_related("usuario")
            .order_by("-creado_en")[:30]
        )

        entradas_hoy = (
            RetiroCaja.objects
            .filter(local=local, fecha=hoy, tipo=RetiroCaja.Tipo.ENTRADA)
            .aggregate(total=Coalesce(Sum("monto"), Decimal("0.00")))
        )["total"] or Decimal("0.00")

        salidas_hoy = (
            RetiroCaja.objects
            .filter(local=local, fecha=hoy, tipo=RetiroCaja.Tipo.SALIDA)
            .aggregate(total=Coalesce(Sum("monto"), Decimal("0.00")))
        )["total"] or Decimal("0.00")

        return render(request, self.template_name, {
            "local_activo": local,
            "hoy": hoy,
            "saldo_actual": saldo_actual,
            "movimientos_hoy": movimientos_hoy,
            "entradas_hoy": entradas_hoy,
            "salidas_hoy": salidas_hoy,
            "puede_agregar_efectivo": request.user.is_staff,
        })
        
    def post(self, request):
        local = _get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos_caja")

        hoy = timezone.localdate()

        accion = (request.POST.get("accion") or "salida").strip().lower()
        monto_raw = (request.POST.get("monto") or "").strip()
        nota = (request.POST.get("nota") or "").strip()
        motivo = (request.POST.get("motivo") or RetiroCaja.Motivo.OTRO).strip().upper()

        try:
            monto = Decimal(monto_raw)
        except (InvalidOperation, TypeError):
            messages.error(request, "Monto inválido.")
            return redirect("inventory:pos_caja")

        if monto <= 0:
            messages.error(request, "El monto debe ser mayor a 0.")
            return redirect("inventory:pos_caja")

        motivos_validos = {c for c, _ in RetiroCaja.Motivo.choices}
        if motivo not in motivos_validos:
            motivo = RetiroCaja.Motivo.OTRO

        if accion == "entrada":
            if not request.user.is_staff:
                messages.error(request, "Solo un administrador puede agregar efectivo.")
                return redirect("inventory:pos_caja")

            if motivo == RetiroCaja.Motivo.GUARDAR:
                motivo = RetiroCaja.Motivo.APORTE

            RetiroCaja.objects.create(
                local=local,
                usuario=request.user,
                fecha=hoy,
                tipo=RetiroCaja.Tipo.ENTRADA,
                monto=monto,
                motivo=motivo,
                nota=nota,
            )

            messages.success(request, f"Ingreso de efectivo registrado: $ {monto:.2f}")
            return redirect("inventory:pos_caja")

        saldo_disponible = _saldo_caja_local(local)
        if monto > saldo_disponible:
            messages.error(
                request,
                f"No alcanza el efectivo disponible. Disponible: $ {saldo_disponible:.2f}"
            )
            return redirect("inventory:pos_caja")

        RetiroCaja.objects.create(
            local=local,
            usuario=request.user,
            fecha=hoy,
            tipo=RetiroCaja.Tipo.SALIDA,
            monto=monto,
            motivo=motivo,
            nota=nota,
        )

        messages.success(request, f"Retiro registrado: $ {monto:.2f}")
        return redirect("inventory:pos_caja")

class POSAddItemByBarcodeView(LoginRequiredMixin, View):
    def post(self, request):
        dev = _get_devolucion(request.session)
        if dev is not None and not dev.get("articulo_devuelto_id"):
            messages.error(request, "Primero seleccioná el producto que trae el cliente para la devolución.")
            return redirect("inventory:pos")

        barcode = (request.POST.get("barcode") or "").strip()
        if not barcode:
            messages.error(request, "Escaneá un código de barras.")
            return redirect("inventory:pos")

        local = _get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")

        qs = (
            Articulo.objects
            .select_related("product_id", "product_id__marca")
            .filter(
                local=local,
                barcode=barcode,
                estado=Articulo.Estado.DISPONIBLE
            )
            .order_by("articulo_id")
        )

        art = qs.first()
        if not art:
            messages.error(request, f"No hay unidades disponibles para el código {barcode}.")
            return redirect("inventory:pos")

        disponibles = qs.count()
        line_key = f"{barcode}|{art.talle}|{art.color}"
        cart = _get_cart(request.session)

        current_qty = int(cart.get(line_key, {}).get("qty", 0))
        new_qty = current_qty + 1

        if new_qty > disponibles:
            messages.error(request, f"No hay stock suficiente. Disponibles: {disponibles}.")
            return redirect("inventory:pos")

        precio_base = Decimal(art.product_id.precio)
        promo, promo_data = get_mejor_promocion_para_producto(art.product_id, qty=new_qty)
        descuento_total_linea = promo_data["descuento"] if promo_data else Decimal("0")
        precio_final_unit = promo_data["precio_final"] if promo_data else precio_base

        subtotal_bruto = precio_base * new_qty
        total_linea = subtotal_bruto - descuento_total_linea

        marca_obj = getattr(art.product_id, "marca", None)
        marca_nombre = getattr(marca_obj, "nombre", "") if marca_obj else ""

        cart[line_key] = {
            "producto_id": art.product_id.product_id,
            "producto_nombre": art.product_id.nombre,
            "marca": marca_nombre,
            "sku": art.sku,
            "barcode": art.barcode,
            "talle": art.talle,
            "color": art.color,

            "qty": new_qty,

            "precio_base": str(precio_base),
            "precio_final_unit": str(precio_final_unit),
            "descuento_total_linea": str(descuento_total_linea),
            "subtotal_bruto": str(subtotal_bruto),
            "total_linea": str(total_linea),

            "promocion_id": promo.promocion_id if promo else None,
            "promocion_nombre": promo.nombre if promo else "",
        }

        _save_cart(request.session, cart)
        return redirect("inventory:pos")

class POSRemoveItemView(LoginRequiredMixin, View):
    def post(self, request):
        key = request.POST.get("key") or ""
        cart = _get_cart(request.session)
        if key in cart:
            del cart[key]
            _save_cart(request.session, cart)
        return redirect("inventory:pos")
    
class POSClearView(LoginRequiredMixin, View):
    def get(self, request):
        _save_cart(request.session, {})
        return redirect("inventory:pos")
    
    def post(self, request):
        _save_cart(request.session, {})
        return redirect("inventory:pos")
    
class POSCheckoutView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos_checkout.html"

    def get(self, request):
        form = CheckoutForm()
        cart = _get_cart(request.session)
        if not cart:
            messages.info(request, "El carrito está vacío.")
            return redirect("inventory:pos")

        totals = _cart_totals(cart)
        dev = _get_devolucion(request.session)

        credito_total = Decimal("0.00")
        diferencia_cobrar = totals["subtotal_final"]
        if dev and dev.get("articulo_devuelto_id"):
            credito_total = Decimal(dev.get("credito_total", "0") or "0")
            diferencia_cobrar = totals["subtotal_final"] - credito_total
            if diferencia_cobrar < 0:
                diferencia_cobrar = Decimal("0.00")

        return render(request, self.template_name, {
            "form": form,
            "cart": cart,
            "subtotal_base": totals["subtotal_base"],
            "total_descuento": totals["total_descuento"],
            "total": totals["subtotal_final"],
            "devolucion_data": dev,
            "devolucion_activa": bool(dev),
            "credito_total": credito_total,
            "diferencia_cobrar": diferencia_cobrar,
        })

    @transaction.atomic
    def post(self, request):
        dev = _get_devolucion(request.session)
        if dev and dev.get("articulo_devuelto_id"):
            return self._post_devolucion(request)
        return self._post_normal(request)

    def _render_checkout_with_form(self, request, form, cart):
        totals = _cart_totals(cart)
        dev = _get_devolucion(request.session)

        credito_total = Decimal("0.00")
        diferencia_cobrar = totals["subtotal_final"]
        if dev and dev.get("articulo_devuelto_id"):
            credito_total = Decimal(dev.get("credito_total", "0") or "0")
            diferencia_cobrar = totals["subtotal_final"] - credito_total
            if diferencia_cobrar < 0:
                diferencia_cobrar = Decimal("0.00")

        return render(request, self.template_name, {
            "form": form,
            "cart": cart,
            "subtotal_base": totals["subtotal_base"],
            "total_descuento": totals["total_descuento"],
            "total": totals["subtotal_final"],
            "devolucion_data": dev,
            "devolucion_activa": bool(dev),
            "credito_total": credito_total,
            "diferencia_cobrar": diferencia_cobrar,
        })

    def _post_normal(self, request):
        cart = _get_cart(request.session)
        if not cart:
            messages.error(request, "El carrito está vacío.")
            return redirect("inventory:pos")

        local = _get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")

        form = CheckoutForm(request.POST)
        if not form.is_valid():
            return self._render_checkout_with_form(request, form, cart)

        metodo_de_pago = form.cleaned_data["metodo_pago"]

        venta = Venta.objects.create(
            usuario=request.user,
            local=local,
            estado=Venta.Estado.ABIERTA,
            metodo_de_pago=metodo_de_pago
        )

        subtotal_base = Decimal("0.00")
        subtotal_final = Decimal("0.00")
        descuento_total = Decimal("0.00")
        profit_total = Decimal("0.00")
        hay_costos_desconocidos = False

        for it in cart.values():
            barcode = it["barcode"]
            qty = int(it["qty"])
            qty_d = Decimal(qty)

            precio_base = Decimal(it["precio_base"])
            descuento_total_linea = Decimal(it.get("descuento_total_linea", "0"))
            promocion_id = it.get("promocion_id")
            promocion_nombre = it.get("promocion_nombre", "")

            disponibles_qs = (
                Articulo.objects
                .select_for_update()
                .filter(local=local, barcode=barcode, estado=Articulo.Estado.DISPONIBLE)
                .order_by("articulo_id")
            )

            articulos = list(disponibles_qs[:qty])
            if len(articulos) < qty:
                raise ValueError(
                    f"Stock insuficiente para barcode {barcode}. Pediste {qty}, hay {len(articulos)}."
                )

            costos_articulos = [getattr(a.ingreso_item, "costo_unitario", None) for a in articulos]
            if any(c is None for c in costos_articulos):
                costo_total = None
                costo_unitario_prom = None
                profit_linea = None
                hay_costos_desconocidos = True
            else:
                costo_total = sum(Decimal(c) for c in costos_articulos)
                costo_unitario_prom = (costo_total / qty_d) if qty else Decimal("0.00")

            total_linea_base = precio_base * qty_d
            total_linea = total_linea_base - descuento_total_linea
            precio_unitario_real = (total_linea / qty_d) if qty else Decimal("0.00")
            if costo_total is not None:
                profit_linea = total_linea - costo_total

            subtotal_base += total_linea_base
            subtotal_final += total_linea
            descuento_total += descuento_total_linea
            if profit_linea is not None:
                profit_total += profit_linea

            promo_obj = None
            if promocion_id:
                promo_obj = Promocion.objects.filter(pk=promocion_id).first()

            descuento_unitario_prom = (descuento_total_linea / qty_d) if qty else Decimal("0.00")

            VentaItem.objects.create(
                venta=venta,
                producto_id=it["producto_id"],
                sku=it["sku"],
                barcode=barcode,
                talle=int(it["talle"]),
                color=it["color"],
                cantidad=qty,
                precio_base_unitario=precio_base,
                descuento_unitario=descuento_unitario_prom,
                precio_unitario=precio_unitario_real,
                costo_unitario=costo_unitario_prom,
                profit_linea=profit_linea,
                total_linea=total_linea,
                promocion=promo_obj,
                promocion_nombre=promocion_nombre,
            )

            movs = []
            venta_articulos = []

            for a in articulos:
                costo_u = getattr(a.ingreso_item, "costo_unitario", None) if a.ingreso_item else None
                profit_u = (precio_unitario_real - Decimal(costo_u)) if costo_u is not None else None

                movs.append(MovimientoStock(
                    tipo=MovimientoStock.Tipo.VENTA,
                    local=local,
                    usuario=request.user,
                    articulo=a,
                    producto=a.product_id,
                    barcode=a.barcode,
                    sku=a.sku,
                    talle=a.talle,
                    color=a.color,
                    cantidad=-1,
                    costo_unitario=costo_u,
                    precio_unitario=precio_unitario_real,
                    profit_unitario=profit_u,
                    ingreso=None,
                    venta=venta,
                    nota=f"Venta #{venta.venta_id}",
                ))

                venta_articulos.append(VentaArticulo(venta=venta, articulo=a))

            Articulo.objects.filter(
                articulo_id__in=[a.articulo_id for a in articulos]
            ).update(estado=Articulo.Estado.VENDIDO)

            VentaArticulo.objects.bulk_create(venta_articulos)
            MovimientoStock.objects.bulk_create(movs)

        venta.subtotal = subtotal_base
        venta.total_descuento = descuento_total
        venta.total = subtotal_final
        venta.profit_total = None if hay_costos_desconocidos else profit_total
        venta.estado = Venta.Estado.CERRADA
        venta.save(update_fields=[
            "subtotal",
            "total_descuento",
            "total",
            "profit_total",
            "estado",
        ])

        _save_cart(request.session, {})

        messages.success(request, f"Venta #{venta.venta_id} cerrada. Total: $ {venta.total}")
        return redirect("inventory:pos")

    def _post_devolucion(self, request):
        cart = _get_cart(request.session)
        dev = _get_devolucion(request.session)

        if not cart:
            messages.error(request, "El carrito está vacío.")
            return redirect("inventory:pos")

        if not dev or not dev.get("articulo_devuelto_id"):
            messages.error(request, "No hay devolución activa.")
            return redirect("inventory:pos")

        local = _get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")

        form = CheckoutForm(request.POST)
        if not form.is_valid():
            return self._render_checkout_with_form(request, form, cart)

        metodo_de_pago = form.cleaned_data["metodo_pago"]

        articulo_devuelto = (
            Articulo.objects
            .select_for_update()
            .get(articulo_id=dev["articulo_devuelto_id"])
        )

        if articulo_devuelto.estado != Articulo.Estado.VENDIDO:
            messages.error(request, "El producto devuelto ya no está en estado vendido.")
            return redirect("inventory:pos")

        if _articulo_ya_devuelto(articulo_devuelto):
            messages.error(request, "Ese producto ya fue devuelto anteriormente.")
            return redirect("inventory:pos")

        totals = _cart_totals(cart)
        subtotal_base = totals["subtotal_base"]
        subtotal_final = totals["subtotal_final"]
        descuento_total = totals["total_descuento"]

        credito_total = Decimal(dev.get("credito_total", "0") or "0")
        diferencia = subtotal_final - credito_total

        if diferencia < 0:
            messages.error(request, "La devolución no puede quedar a favor del cliente.")
            return redirect("inventory:pos")

        venta = Venta.objects.create(
            usuario=request.user,
            local=local,
            estado=Venta.Estado.ABIERTA,
            metodo_de_pago=metodo_de_pago
        )

        profit_total = Decimal("0.00")
        hay_costos_desconocidos = False
        credito_restante = credito_total

        # 1) entra el producto devuelto
        articulo_devuelto.estado = Articulo.Estado.DISPONIBLE
        articulo_devuelto.local = local
        articulo_devuelto.save(update_fields=["estado", "local"])

        costo_devuelto = getattr(articulo_devuelto.ingreso_item, "costo_unitario", None)

        MovimientoStock.objects.create(
            tipo=MovimientoStock.Tipo.DEVOLUCION,
            local=local,
            usuario=request.user,
            articulo=articulo_devuelto,
            producto=articulo_devuelto.product_id,
            barcode=articulo_devuelto.barcode,
            sku=articulo_devuelto.sku,
            talle=articulo_devuelto.talle,
            color=articulo_devuelto.color,
            cantidad=1,
            costo_unitario=costo_devuelto,
            precio_unitario=credito_total,
            profit_unitario=Decimal("0.00"),
            ingreso=None,
            venta=venta,
            nota=f"Devolución / cambio asociada a Venta #{venta.venta_id}",
        )

        # 2) salen los productos nuevos
        for it in cart.values():
            barcode = it["barcode"]
            qty = int(it["qty"])
            qty_d = Decimal(qty)

            precio_base = Decimal(it["precio_base"])
            descuento_total_linea = Decimal(it.get("descuento_total_linea", "0"))
            promocion_id = it.get("promocion_id")
            promocion_nombre = it.get("promocion_nombre", "")

            disponibles_qs = (
                Articulo.objects
                .select_for_update()
                .filter(local=local, barcode=barcode, estado=Articulo.Estado.DISPONIBLE)
                .order_by("articulo_id")
            )

            articulos = list(disponibles_qs[:qty])
            if len(articulos) < qty:
                raise ValueError(
                    f"Stock insuficiente para barcode {barcode}. Pediste {qty}, hay {len(articulos)}."
                )

            costos_articulos = [getattr(a.ingreso_item, "costo_unitario", None) for a in articulos]
            if any(c is None for c in costos_articulos):
                costo_total = None
                costo_unitario_prom = None
                profit_linea = None
                hay_costos_desconocidos = True
            else:
                costo_total = sum(Decimal(c) for c in costos_articulos)
                costo_unitario_prom = (costo_total / qty_d) if qty else Decimal("0.00")

            total_linea_base = precio_base * qty_d
            total_linea_con_promo = total_linea_base - descuento_total_linea

            # Crédito por devolución repartido como descuento adicional
            credito_aplicado_linea = min(credito_restante, total_linea_con_promo)
            credito_restante -= credito_aplicado_linea

            descuento_total_linea_final = descuento_total_linea + credito_aplicado_linea
            total_linea = total_linea_con_promo - credito_aplicado_linea

            precio_unitario_real = (total_linea / qty_d) if qty else Decimal("0.00")
            if costo_total is not None:
                profit_linea = total_linea - costo_total
                profit_total += profit_linea

            promo_obj = None
            if promocion_id:
                promo_obj = Promocion.objects.filter(pk=promocion_id).first()

            descuento_unitario_prom = (descuento_total_linea_final / qty_d) if qty else Decimal("0.00")

            VentaItem.objects.create(
                venta=venta,
                producto_id=it["producto_id"],
                sku=it["sku"],
                barcode=barcode,
                talle=int(it["talle"]),
                color=it["color"],
                cantidad=qty,
                precio_base_unitario=precio_base,
                descuento_unitario=descuento_unitario_prom,
                precio_unitario=precio_unitario_real,
                costo_unitario=costo_unitario_prom,
                profit_linea=profit_linea,
                total_linea=total_linea,
                promocion=promo_obj,
                promocion_nombre=promocion_nombre,
            )

            movs = []
            venta_articulos = []

            for a in articulos:
                costo_u = getattr(a.ingreso_item, "costo_unitario", None) if a.ingreso_item else None
                profit_u = (precio_unitario_real - Decimal(costo_u)) if costo_u is not None else None

                movs.append(MovimientoStock(
                    tipo=MovimientoStock.Tipo.VENTA,
                    local=local,
                    usuario=request.user,
                    articulo=a,
                    producto=a.product_id,
                    barcode=a.barcode,
                    sku=a.sku,
                    talle=a.talle,
                    color=a.color,
                    cantidad=-1,
                    costo_unitario=costo_u,
                    precio_unitario=precio_unitario_real,
                    profit_unitario=profit_u,
                    ingreso=None,
                    venta=venta,
                    nota=f"Salida por devolución / cambio en Venta #{venta.venta_id}",
                ))

                venta_articulos.append(VentaArticulo(venta=venta, articulo=a))

            Articulo.objects.filter(
                articulo_id__in=[a.articulo_id for a in articulos]
            ).update(estado=Articulo.Estado.VENDIDO)

            VentaArticulo.objects.bulk_create(venta_articulos)
            MovimientoStock.objects.bulk_create(movs)

        venta.subtotal = subtotal_base
        venta.total_descuento = descuento_total + credito_total
        venta.total = diferencia
        venta.profit_total = None if hay_costos_desconocidos else profit_total
        venta.estado = Venta.Estado.CERRADA
        venta.save(update_fields=[
            "subtotal",
            "total_descuento",
            "total",
            "profit_total",
            "estado",
        ])

        _save_cart(request.session, {})
        _clear_devolucion(request.session)

        messages.success(
            request,
            f"Devolución / cambio registrada. Diferencia cobrada: $ {venta.total}"
        )
        return redirect("inventory:pos")

class POSDevolucionStartView(LoginRequiredMixin, View):
    def post(self, request):
        local = _get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")

        _save_cart(request.session, {})
        _save_devolucion(request.session, {
            "local_id": local.local_id,
            "articulo_devuelto_id": None,
            "venta_origen_id": None,
            "credito_total": "0.00",
            "barcode": "",
            "sku": "",
            "producto_nombre": "",
            "marca": "",
            "talle": "",
            "color": "",
        })

        messages.success(request, "Modo devolución activado.")
        return redirect("inventory:pos")


class POSDevolucionCancelView(LoginRequiredMixin, View):
    def post(self, request):
        _clear_devolucion(request.session)
        _save_cart(request.session, {})
        messages.success(request, "Devolución cancelada.")
        return redirect("inventory:pos")


class POSDevolucionSetReturnedView(LoginRequiredMixin, View):
    def post(self, request):
        dev = _get_devolucion(request.session)
        if dev is None:
            messages.error(request, "Primero iniciá una devolución.")
            return redirect("inventory:pos")

        articulo_id = request.POST.get("articulo_id")
        if not articulo_id:
            messages.error(request, "No se seleccionó el producto devuelto.")
            return redirect("inventory:pos")

        articulo = get_object_or_404(
            Articulo.objects.select_related("product_id", "product_id__marca", "local"),
            articulo_id=articulo_id,
        )

        if articulo.estado != Articulo.Estado.VENDIDO:
            messages.error(request, "Solo se pueden devolver productos vendidos.")
            return redirect("inventory:pos")

        if _articulo_ya_devuelto(articulo):
            messages.error(request, "Ese producto ya fue devuelto anteriormente.")
            return redirect("inventory:pos")

        credito, venta_origen = _get_credito_devolucion(articulo)

        marca_obj = getattr(articulo.product_id, "marca", None)
        marca_nombre = getattr(marca_obj, "nombre", "") if marca_obj else ""

        dev.update({
            "articulo_devuelto_id": articulo.articulo_id,
            "venta_origen_id": venta_origen.venta_id if venta_origen else None,
            "credito_total": str(credito),
            "barcode": articulo.barcode or "",
            "sku": articulo.sku or "",
            "producto_nombre": articulo.product_id.nombre if articulo.product_id else "",
            "marca": marca_nombre,
            "talle": articulo.talle,
            "color": articulo.color or "",
        })
        _save_devolucion(request.session, dev)

        messages.success(request, f"Producto devuelto seleccionado. Crédito: $ {credito}")
        return redirect("inventory:pos")
