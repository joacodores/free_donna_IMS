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


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def money(x):
    if x is None:
        x = Decimal("0.00")
    return f"$ {Decimal(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def money_or_dash(x):
    return "—" if x is None else money(x)


def safe(s, maxlen=80):
    s = "" if s is None else str(s)
    return s[:maxlen]


def ensure_space(c, w, h, y, min_y=70, repeat_header_fn=None):
    if y < min_y:
        c.showPage()
        if repeat_header_fn:
            return repeat_header_fn()
        return h - 60
    return y

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

def ar_dt(dt):
    if dt is None:
        return None

    # Si Django lo tiene como aware, convertir a hora Argentina
    if timezone.is_aware(dt):
        return dt.astimezone(AR_TZ)

    # Si viene naive, asumir que ya está en hora local del negocio
    return dt

def fmt_ar_dt(dt):
    dt = ar_dt(dt)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"

def fmt_ar_date(dt):
    dt = ar_dt(dt)
    return dt.strftime("%Y-%m-%d") if dt else "-"


def _norm(s):
    return (str(s).strip() if s is not None else "")

def _to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def _to_decimal(value):
    if value is None or value == "":
        return None
    try:
        txt = str(value).strip().replace("$", "").replace(" ", "")
        txt = txt.replace(".", "").replace(",", ".") if "," in txt and "." in txt else txt.replace(",", ".")
        return Decimal(txt)
    except (InvalidOperation, ValueError):
        return None

def _norm_text(value):
    return " ".join(str(value or "").strip().split())

def _barcode_conflict(local, barcode, producto, talle, color):
    color_norm = _norm_text(color).lower()

    existente = (
        Articulo.objects
        .select_related("product_id")
        .filter(local=local, barcode=barcode)
        .order_by("-articulo_id")
        .first()
    )

    if not existente:
        return None

    mismo_producto = existente.product_id_id == producto.pk
    mismo_talle = existente.talle == talle
    mismo_color = _norm_text(existente.color).lower() == color_norm

    if mismo_producto and mismo_talle and mismo_color:
        return None

    return existente

def _articulos_visibles_qs(request):
    qs = Articulo.objects.select_related("product_id", "product_id__marca", "local")

    if not _should_show_all_locals(request):
        local_id = request.session.get("local_id")
        if local_id:
            qs = qs.filter(local_id=local_id)

    return qs

def _should_show_all_locals(request):
    return (request.GET.get("all_locals") == "1")

CART_KEY = "pos_cart"

def _get_cart(session):
    return session.get(CART_KEY, {})

def _save_cart(session, cart):
    session[CART_KEY] = cart
    session.modified = True
    
def _cart_totals(cart):
    subtotal_base = Decimal("0.00")
    total_descuento = Decimal("0.00")
    total = Decimal("0.00")

    for it in cart.values():
        qty = int(it["qty"])
        precio_base = Decimal(it["precio_base"])
        descuento_total_linea = Decimal(it.get("descuento_total_linea", "0"))

        subtotal_linea = precio_base * qty
        total_linea = subtotal_linea - descuento_total_linea

        it["subtotal_bruto"] = str(subtotal_linea)
        it["total_linea"] = str(total_linea)

        subtotal_base += subtotal_linea
        total_descuento += descuento_total_linea
        total += total_linea

    return {
        "subtotal_base": subtotal_base,
        "total_descuento": total_descuento,
        "subtotal_final": total,
    }


def _get_local_activo(request):
    local_id = request.session.get("local_id")
    if not local_id:
        return None
    local = Local.objects.filter(local_id=local_id).first()
    if local is None:
        # La sesión apunta a un local inexistente (p. ej. borrado): la limpiamos
        # en vez de dejar que Local.DoesNotExist tire un 500.
        request.session.pop("local_id", None)
        request.session.modified = True
    return local

def _saldo_caja_local(local):
    if not local:
        return Decimal("0.00")

    ventas_efectivo = (
        Venta.objects
        .filter(
            local=local,
            estado=Venta.Estado.CERRADA,
            metodo_de_pago=Venta.MetodoPago.EFECTIVO,
        )
        .aggregate(total=Coalesce(Sum("total"), Decimal("0.00")))
    )["total"] or Decimal("0.00")

    entradas = (
        RetiroCaja.objects
        .filter(local=local, tipo=RetiroCaja.Tipo.ENTRADA)
        .aggregate(total=Coalesce(Sum("monto"), Decimal("0.00")))
    )["total"] or Decimal("0.00")

    salidas = (
        RetiroCaja.objects
        .filter(local=local, tipo=RetiroCaja.Tipo.SALIDA)
        .aggregate(total=Coalesce(Sum("monto"), Decimal("0.00")))
    )["total"] or Decimal("0.00")

    saldo = ventas_efectivo + entradas - salidas
    return saldo if saldo > 0 else Decimal("0.00")

DEV_KEY = "pos_devolucion"


def _get_devolucion(session):
    return session.get(DEV_KEY)


def _save_devolucion(session, data):
    session[DEV_KEY] = data
    session.modified = True


def _clear_devolucion(session):
    session.pop(DEV_KEY, None)
    session.modified = True


def _devolucion_activa(session):
    dev = _get_devolucion(session)
    return bool(dev and dev.get("articulo_devuelto_id"))


def _articulo_ya_devuelto(articulo):
    return MovimientoStock.objects.filter(
        articulo=articulo,
        tipo=MovimientoStock.Tipo.DEVOLUCION,
    ).exists()


def _get_credito_devolucion(articulo):
    mov = (
        MovimientoStock.objects
        .filter(
            articulo=articulo,
            tipo=MovimientoStock.Tipo.VENTA,
            venta__isnull=False,
        )
        .select_related("venta")
        .order_by("-fecha", "-movimiento_id")
        .first()
    )

    if mov and mov.precio_unitario is not None:
        return Decimal(mov.precio_unitario), mov.venta

    precio = Decimal(getattr(articulo.product_id, "precio", 0) or 0)
    return precio, None

def build_sku(producto, color: str, talle) -> str:
    nombre = (getattr(producto, "nombre", "") or "").strip()
    color = (color or "").strip()
    talle = str(talle).strip()
    sku = f"{nombre} {color} {talle}".strip()

    sku = " ".join(sku.split())  

    # truncar por seguridad (tu campo sku en DB suele ser 80)
    return sku[:80]
