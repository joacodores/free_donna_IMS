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

from .utilidades import _get_local_activo, _should_show_all_locals


class MovimientoStockView(LoginRequiredMixin, ListView):
    template_name = "inventory/movimientos/movimientos_list.html"

    def get(self, request):
        show_all = request.user.is_staff and (request.GET.get("all_locals") == "1")
        local = _get_local_activo(request)

        if not show_all and not local:
            return render(request, self.template_name, {
                "error_local": True,
                "mode": "doc",
                "rows": [],
                "tipo": "all",
                "q": "",
                "from": "",
                "to": "",
                "all_locals_active": False,
                "can_export_pdf": False,
            })

        mode = (request.GET.get("mode") or "doc").strip().lower()
        if mode not in ["doc", "day"]:
            mode = "doc"

        if mode == "day" and not request.user.is_staff:
            mode = "doc"

        tipo = (request.GET.get("tipo") or "all").strip().upper()
        q = (request.GET.get("q") or "").strip()
        desde = (request.GET.get("from") or "").strip()
        hasta = (request.GET.get("to") or "").strip()

        base = MovimientoStock.objects.select_related(
            "local", "usuario", "producto", "producto__marca", "venta", "ingreso", "articulo"
        )

        if not show_all:
            base = base.filter(local=local)

        if not request.user.is_staff:
            base = base.filter(usuario=request.user)

        if tipo in ["IN", "OUT", "TRF", "BAJ", "RET"]:
            base = base.filter(tipo=tipo)

        if q:
            base = base.filter(
                Q(barcode__icontains=q) |
                Q(sku__icontains=q) |
                Q(producto__nombre__icontains=q) |
                Q(producto__marca__nombre__icontains=q)
            )

        if desde:
            d = Datetime.strptime(desde, "%Y-%m-%d").date()
            base = base.filter(
                fecha__gte=timezone.make_aware(datetime.combine(d, time.min))
            )

        if hasta:
            h = Datetime.strptime(hasta, "%Y-%m-%d").date()
            base = base.filter(
                fecha__lte=timezone.make_aware(datetime.combine(h, time.max))
            )

        if mode == "doc":
            vals = ["tipo", "venta_id", "ingreso_id", "transferencia_id", "baja_id"]
            if show_all:
                vals += ["local_id", "local__nombre"]

            rows = (
                base.values(*vals)
                .annotate(
                    fecha=Max("fecha"),
                    items=Count("movimiento_id"),
                    unidades=Coalesce(Sum("cantidad"), Value(0, output_field=IntegerField())),
                    venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                    ganancia_total=Sum("profit_unitario"),
                    ganancias_desconocidas=Count("movimiento_id", filter=Q(profit_unitario__isnull=True)),
                )
                .order_by("-fecha")
            )
            rows_data = list(rows)
            for r in rows_data:
                if r["ganancias_desconocidas"]:
                    r["ganancia_total"] = None
                elif r["ganancia_total"] is None:
                    r["ganancia_total"] = Decimal("0.00")

            return render(request, self.template_name, {
                "mode": mode,
                "rows": rows_data,
                "tipo": tipo,
                "q": q,
                "from": desde,
                "to": hasta,
                "all_locals_active": show_all,
                "can_export_pdf": request.user.is_staff and mode == "doc" and tipo in ["IN", "OUT"],
            })

        qs = base.annotate(dia=TruncDate("fecha"))
        vals = ["dia"]
        if show_all:
            vals += ["local_id", "local__nombre"]

        rows = (
            qs.values(*vals)
            .annotate(
                unidades_out=Coalesce(
                    Sum("cantidad", filter=Q(tipo="OUT")),
                    Value(0, output_field=IntegerField())
                ),
                unidades_in=Coalesce(
                    Sum("cantidad", filter=Q(tipo="IN")),
                    Value(0, output_field=IntegerField())
                ),
                venta_total=Coalesce(
                    Sum("precio_unitario", filter=Q(tipo="OUT")),
                    Value(0, output_field=DecimalField())
                ),
                ganancia_total=Sum("profit_unitario", filter=Q(tipo="OUT")),
                ganancias_desconocidas=Count("movimiento_id", filter=Q(tipo="OUT", profit_unitario__isnull=True)),
            )
            .order_by("-dia")
        )
        rows_data = list(rows)
        for r in rows_data:
            if r["ganancias_desconocidas"]:
                r["ganancia_total"] = None
            elif r["ganancia_total"] is None:
                r["ganancia_total"] = Decimal("0.00")

        return render(request, self.template_name, {
            "mode": mode,
            "rows": rows_data,
            "tipo": tipo,
            "q": q,
            "from": desde,
            "to": hasta,
            "all_locals_active": show_all,
            "can_export_pdf": False,
        })
