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

from .utilidades import _get_local_activo


class VentaDetailView(LoginRequiredMixin, DetailView):
    model = Venta
    template_name = "inventory/movimientos/venta_detail.html"
    context_object_name = "venta"
    pk_url_kwarg = "venta_id"
    
    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = Venta.objects.select_related("usuario", "local")
        obj = get_object_or_404(qs, venta_id=self.kwargs["venta_id"])
        if local and obj.local_id != local.local_id:
            raise get_object_or_404(Venta, venta_id=-1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        venta = ctx["venta"]

        items = list(
            venta.items
            .select_related("producto", "producto__marca", "promocion")
            .all()
            .order_by("item_id")
        )
        ctx["items"] = items

        unidades = (
            MovimientoStock.objects
            .select_related("articulo", "producto")
            .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
            .order_by("movimiento_id")
        )
        ctx["unidades"] = unidades

        agg = (
            MovimientoStock.objects
            .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
            .aggregate(
                unidades=Count("movimiento_id"),
                costo_total=Sum("costo_unitario"),
                venta_total=Coalesce(Sum("precio_unitario"), Decimal("0.00")),
                profit_total=Sum("profit_unitario"),
                costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
                ganancias_desconocidas=Count("movimiento_id", filter=Q(profit_unitario__isnull=True)),
            )
        )

        costo_total = None if agg["costos_desconocidos"] else (agg["costo_total"] or Decimal("0.00"))
        profit_total = None if agg["ganancias_desconocidas"] else (agg["profit_total"] or Decimal("0.00"))
        ctx["ms_totals"] = {
            "unidades": agg["unidades"] or 0,
            "costo_total": costo_total,
            "venta_total": agg["venta_total"] or Decimal("0.00"),
            "profit_total": profit_total,
        }

        ctx["sale_totals"] = {
            "subtotal": venta.subtotal or Decimal("0.00"),
            "descuento_total": getattr(venta, "total_descuento", Decimal("0.00")) or Decimal("0.00"),
            "total": venta.total or Decimal("0.00"),
            "profit_total": venta.profit_total,
        }

        return ctx
    
class IngresoDetailView(LoginRequiredMixin, DetailView):
    model = Ingreso
    template_name = "inventory/movimientos/ingreso_detail.html"
    context_object_name = "ingreso"
    pk_url_kwarg = "ingreso_id"

    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = Ingreso.objects.select_related("usuario", "local")
        obj = get_object_or_404(qs, ingreso_id=self.kwargs["ingreso_id"])
        if local and obj.local_id != local.local_id:
            raise get_object_or_404(Ingreso, ingreso_id=-1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ingreso = ctx["ingreso"]

        items = list(ingreso.items.all().order_by("item_id"))
        ctx["items"] = items

        unidades = (MovimientoStock.objects
                    .select_related("articulo")
                    .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
                    .order_by("movimiento_id"))
        ctx["unidades"] = unidades

        agg = (MovimientoStock.objects
               .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
               .aggregate(
                   unidades=Count("movimiento_id"),
                   costo_total=Sum("costo_unitario"),
                   costos_desconocidos=Count("movimiento_id", filter=Q(costo_unitario__isnull=True)),
                ))
        costo_total = None if agg["costos_desconocidos"] else (agg["costo_total"] or Decimal("0.00"))
        ctx["ms_totals"] = {
            "unidades": agg["unidades"] or 0,
            "costo_total": costo_total,
        }
        return ctx

class BajaDetailView(LoginRequiredMixin, DetailView):
    model = BajaStock
    template_name = "inventory/movimientos/baja_detail.html"
    context_object_name = "baja"
    pk_url_kwarg = "baja_id"

    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = BajaStock.objects.select_related("usuario", "local")
        obj = get_object_or_404(qs, baja_id=self.kwargs["baja_id"])
        if local and obj.local_id != local.local_id:
            raise get_object_or_404(BajaStock, baja_id=-1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        baja = ctx["baja"]

        unidades = (MovimientoStock.objects
                    .select_related("articulo")
                    .filter(baja=baja, tipo=MovimientoStock.Tipo.BAJA)
                    .order_by("movimiento_id"))
        ctx["unidades"] = unidades

        items_map = {}
        total_unidades = 0
        total_costo = Decimal("0.00")
        tiene_costos_desconocidos = False

        for m in unidades:
            key = (m.sku, m.barcode, m.talle, m.color)
            qty = int(m.cantidad or 0)
            cu = m.costo_unitario
            line = (Decimal(cu) * qty) if cu is not None else None

            total_unidades += qty
            if line is None:
                tiene_costos_desconocidos = True
            else:
                total_costo += line

            if key not in items_map:
                items_map[key] = {
                    "sku": m.sku,
                    "barcode": m.barcode,
                    "talle": m.talle,
                    "color": m.color,
                    "cantidad": 0,
                    "total_linea": Decimal("0.00"),
                    "has_unknown_cost": False,
                }

            items_map[key]["cantidad"] += qty
            if line is None:
                items_map[key]["has_unknown_cost"] = True
            else:
                items_map[key]["total_linea"] += line

        items = list(items_map.values())
        for it in items:
            if it["has_unknown_cost"]:
                it["costo_unitario"] = None
                it["total_linea"] = None
            elif it["cantidad"] > 0:
                it["costo_unitario"] = (it["total_linea"] / it["cantidad"]).quantize(Decimal("0.01"))
            else:
                it["costo_unitario"] = Decimal("0.00")

        ctx["items"] = items
        ctx["ms_totals"] = {"unidades": total_unidades, "costo_total": None if tiene_costos_desconocidos else total_costo}
        return ctx
