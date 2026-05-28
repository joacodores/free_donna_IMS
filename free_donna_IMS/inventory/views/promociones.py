from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.db import transaction

from ..models import Promocion, ProductoBulkAdjust, ProductoBulkAdjustItem, Producto
from ..forms import PromocionForm


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def _parse_pct(val: str):
    val = (val or "").strip()
    if val == "":
        return None
    try:
        return Decimal(val.replace(",", "."))
    except Exception:
        return "ERR"


def _apply_pct(value: Decimal, pct: Decimal) -> Decimal:
    factor = Decimal("1") + (pct / Decimal("100"))
    newv = (value * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if newv < 0:
        newv = Decimal("0.00")
    return newv


def _add_query_param(url, key, value):
    u = urlparse(url)
    q = dict(parse_qsl(u.query))
    q[key] = str(value)
    new_query = urlencode(q)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def promocion_aplica_a_producto(promocion, producto):
    if not promocion.esta_vigente():
        return False

    if promocion.aplica_a_todos:
        return True

    if getattr(producto, "marca_id", None) and promocion.marcas.filter(pk=producto.marca_id).exists():
        return True

    if promocion.productos.filter(product_id=producto.product_id).exists():
        return True

    return False


def calcular_precio_con_promocion(producto, promo, qty=1):
    precio = Decimal(producto.precio)

    if promo.tipo_descuento == Promocion.TipoDescuento.PORCENTAJE:
        valor = promo.valor or Decimal("0")
        desc_unit = (valor / Decimal("100")) * precio
        return {
            "precio_final": precio - desc_unit,
            "descuento": desc_unit * qty,
        }

    if promo.tipo_descuento == Promocion.TipoDescuento.MONTO_FIJO:
        valor = promo.valor or Decimal("0")
        desc_unit = min(precio, valor)
        return {
            "precio_final": precio - desc_unit,
            "descuento": desc_unit * qty,
        }

    if promo.tipo_descuento == Promocion.TipoDescuento.ESCALON:
        unidad_obj = promo.unidad_objetivo or 0
        porc = promo.descuento_porcentaje or Decimal("0")

        if unidad_obj < 2 or porc <= 0:
            return {
                "precio_final": precio,
                "descuento": Decimal("0"),
            }

        if qty < unidad_obj:
            return {
                "precio_final": precio,
                "descuento": Decimal("0"),
            }

        descuento_una_unidad = (porc / Decimal("100")) * precio

        return {
            "precio_final": precio,
            "descuento": descuento_una_unidad,
        }

    return {
        "precio_final": precio,
        "descuento": Decimal("0"),
    }


def get_promociones_activas():
    ahora = timezone.now()
    qs = Promocion.objects.filter(estado=Promocion.Estado.ACTIVA).prefetch_related("marcas", "productos")

    # filtrado fino de fechas en Python por simplicidad y claridad
    return [p for p in qs if p.esta_vigente()]


def get_mejor_promocion_para_producto(producto, qty=1):
    promos = get_promociones_activas()

    mejor = None
    mejor_resultado = None

    for promo in promos:
        if not promocion_aplica_a_producto(promo, producto):
            continue

        resultado = calcular_precio_con_promocion(producto, promo, qty)

        if resultado["descuento"] <= Decimal("0"):
            continue

        if mejor is None:
            mejor = promo
            mejor_resultado = resultado
            continue

        if resultado["descuento"] > mejor_resultado["descuento"]:
            mejor = promo
            mejor_resultado = resultado
        elif resultado["descuento"] == mejor_resultado["descuento"]:
            if promo.prioridad > mejor.prioridad:
                mejor = promo
                mejor_resultado = resultado

    return mejor, mejor_resultado


class ProductoBulkAdjustPreviewView(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request):
        marca_id = (request.GET.get("marca_id") or "").strip()
        pct_precio = _parse_pct(request.GET.get("pct_precio"))
        pct_costo  = _parse_pct(request.GET.get("pct_costo"))

        if not marca_id:
            return JsonResponse({"ok": False, "error": "Seleccioná una marca."}, status=400)

        if pct_precio == "ERR" or pct_costo == "ERR":
            return JsonResponse({"ok": False, "error": "Porcentaje inválido."}, status=400)

        if pct_precio is None and pct_costo is None:
            return JsonResponse({"ok": False, "error": "Ingresá % en precio y/o costo."}, status=400)

        marca = get_object_or_404(Producto, pk=marca_id)
        qs = Producto.objects.filter(marca=marca).order_by("product_id")

        total = qs.count()
        sample = list(qs[:5])

        items = []
        for p in sample:
            old_precio = Decimal(p.precio or 0)
            old_costo = p.costo

            new_precio = _apply_pct(old_precio, pct_precio) if pct_precio is not None else old_precio
            new_costo = _apply_pct(old_costo, pct_costo) if (pct_costo is not None and old_costo is not None) else old_costo

            items.append({
                "id": p.pk,
                "nombre": getattr(p, "nombre", "") or str(p),
                "old_precio": f"{old_precio:.2f}",
                "new_precio": f"{new_precio:.2f}",
                "old_costo": f"{old_costo:.2f}" if old_costo is not None else "—",
                "new_costo": f"{new_costo:.2f}" if new_costo is not None else "—",
            })

        return JsonResponse({
            "ok": True,
            "marca": {"id": marca.pk, "nombre": marca.nombre},
            "total": total,
            "pct_precio": str(pct_precio) if pct_precio is not None else None,
            "pct_costo": str(pct_costo) if pct_costo is not None else None,
            "sample": items,
        })


class ProductoBulkAdjustApplyView(LoginRequiredMixin, StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request):
        marca_id = (request.POST.get("marca_id") or "").strip()
        pct_precio = _parse_pct(request.POST.get("pct_precio"))
        pct_costo  = _parse_pct(request.POST.get("pct_costo"))

        if not marca_id:
            messages.error(request, "Seleccioná una marca.")
            return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

        if pct_precio == "ERR" or pct_costo == "ERR":
            messages.error(request, "Porcentaje inválido.")
            return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

        if pct_precio is None and pct_costo is None:
            messages.error(request, "Ingresá % en precio y/o costo.")
            return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

        marca = get_object_or_404(Producto, pk=marca_id)
        qs = Producto.objects.filter(marca=marca).select_for_update()

        total = qs.count()
        if total == 0:
            messages.warning(request, f"No hay productos para {marca.nombre}.")
            return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

        adjust = ProductoBulkAdjust.objects.create(
            user=request.user,
            marca=marca,
            pct_precio=pct_precio,
            pct_costo=pct_costo,
            afectados=total,
            note="Ajuste masivo por marca desde pantalla de productos",
        )

        items_to_create = []
        # aplicamos y guardamos snapshot exacto
        for p in qs:
            old_precio = Decimal(p.precio or 0)
            old_costo = p.costo

            new_precio = _apply_pct(old_precio, pct_precio) if pct_precio is not None else old_precio
            new_costo = _apply_pct(old_costo, pct_costo) if (pct_costo is not None and old_costo is not None) else old_costo

            # Update producto
            p.precio = new_precio
            p.costo = new_costo
            p.save(update_fields=["precio", "costo"])

            items_to_create.append(ProductoBulkAdjustItem(
                adjust=adjust,
                producto=p,
                old_precio=old_precio,
                old_costo=old_costo,
                new_precio=new_precio,
                new_costo=new_costo,
            ))

        ProductoBulkAdjustItem.objects.bulk_create(items_to_create, batch_size=1000)

        # mensaje con link para deshacer
        undo_url = f"/inventario/productos/ajuste-marca/undo/{adjust.pk}/"  # o reverse() si preferís
        messages.success(
            request,
            f"Ajuste aplicado a {marca.nombre} ({total} productos). "
            f"Si necesitás revertirlo, abrí 'Ajuste por marca' y tocá 'Deshacer último ajuste'."
        )
        referer = request.META.get("HTTP_REFERER")
        fallback = redirect("inventory:producto_list").url  # o reverse(...)
        target = referer or fallback

        target = _add_query_param(target, "last_adjust", adjust.pk)
        target = _add_query_param(target, "last_brand", marca.nombre)
        return redirect(target)


class ProductoBulkAdjustUndoView(LoginRequiredMixin, StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request, adjust_id: int):
        adjust = get_object_or_404(ProductoBulkAdjust, pk=adjust_id)

        if adjust.estado == ProductoBulkAdjust.Estado.DESHECHO:
            messages.warning(request, "Este ajuste ya fue deshecho.")
            return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

        # bloqueamos items/productos
        items = list(adjust.items.select_related("producto").select_for_update())

        for it in items:
            p = it.producto
            # revertimos EXACTO a snapshot
            if it.old_precio is not None:
                p.precio = it.old_precio
            p.costo = it.old_costo
            p.save(update_fields=["precio", "costo"])

        adjust.estado = ProductoBulkAdjust.Estado.DESHECHO
        adjust.save(update_fields=["estado"])

        messages.success(request, f"Ajuste deshecho. Los precios y costos volvieron al estado anterior.")
        return redirect(request.META.get("HTTP_REFERER", "inventory:producto_list"))

    # opcional: permitir GET con confirmación simple (yo prefiero POST)
    def get(self, request, adjust_id: int):
        return HttpResponseForbidden("Usá POST para deshacer.")


class PromocionListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Promocion
    template_name = "inventory/promocion/promocion_list.html"
    context_object_name = "promociones"
    paginate_by = 20

    def get_queryset(self):
        qs = Promocion.objects.prefetch_related("marcas", "productos").all()

        q = (self.request.GET.get("q") or "").strip()
        estado = (self.request.GET.get("estado") or "").strip().upper()

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(descripcion__icontains=q)
            )

        if estado in [Promocion.Estado.ACTIVA, Promocion.Estado.PAUSADA]:
            qs = qs.filter(estado=estado)

        return qs.order_by("-prioridad", "-created_at", "nombre")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["estado"] = (self.request.GET.get("estado") or "").strip().upper()
        return ctx


class PromocionCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Promocion
    form_class = PromocionForm
    template_name = "inventory/promocion/promocion_form.html"
    success_url = reverse_lazy("inventory:promocion_list")

    def form_valid(self, form):
        messages.success(self.request, "Promoción creada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        print("FORM ERRORS:", form.errors)
        print("NON FIELD ERRORS:", form.non_field_errors())
        messages.error(self.request, "No se pudo guardar la promoción. Revisá los campos.")
        return super().form_invalid(form)


class PromocionUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Promocion
    form_class = PromocionForm
    template_name = "inventory/promocion/promocion_form.html"
    pk_url_kwarg = "promocion_id"
    success_url = reverse_lazy("inventory:promocion_list")

    def form_valid(self, form):
        messages.success(self.request, "Promoción actualizada correctamente.")
        return super().form_valid(form)


class PromocionDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = Promocion
    template_name = "inventory/promocion/promocion_detail.html"
    context_object_name = "promocion"
    pk_url_kwarg = "promocion_id"


class PromocionToggleEstadoView(LoginRequiredMixin, StaffRequiredMixin, View):
    def post(self, request, promocion_id):
        promocion = get_object_or_404(Promocion, pk=promocion_id)

        if promocion.estado == Promocion.Estado.ACTIVA:
            promocion.estado = Promocion.Estado.PAUSADA
            msg = "Promoción pausada correctamente."
        else:
            promocion.estado = Promocion.Estado.ACTIVA
            msg = "Promoción activada correctamente."

        promocion.save(update_fields=["estado"])
        messages.success(request, msg)
        return redirect("inventory:promocion_list")


class PromocionDeleteView(LoginRequiredMixin, StaffRequiredMixin, View):
    def post(self, request, promocion_id):
        promo = get_object_or_404(Promocion, promocion_id=promocion_id)
        nombre = promo.nombre
        promo.delete()
        messages.success(request, f'Promoción "{nombre}" eliminada correctamente.')
        return redirect("inventory:promocion_list")
