from ..models import BajaStock, Ingreso, IngresoItem, Local, Marca, MovimientoStock, Producto, Articulo, ProductoBulkAdjust, ProductoBulkAdjustItem, Promocion, RetiroCaja, Transferencia, TransferenciaItem, Venta, VentaItem, VentaArticulo
from .utilidades import StaffRequiredMixin
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.db.models import Q, F, Value, IntegerField, DecimalField, ExpressionWrapper
from decimal import Decimal
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

class MarcaListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Marca
    template_name = "inventory/marca/marca_list.html"
    context_object_name = "marcas"
    paginate_by = 30

    def get_queryset(self):
        q = (self.request.GET.get("q") or "").strip()
        sort = (self.request.GET.get("sort") or "nombre").strip().lower()

        qs = Marca.objects.all()

        if q:
            qs = qs.filter(nombre__icontains=q)

        qs = qs.annotate(productos_count=Count("productos", distinct=True))

        # Ventas GLOBAL: Marca -> Productos -> MovimientoStock (solo VENTA)
        sales_filter = Q(productos__movimientostock__tipo=MovimientoStock.Tipo.VENTA)

        qs = qs.annotate(
            unidades_raw=Coalesce(
                Sum("productos__movimientostock__cantidad", filter=sales_filter),
                Value(0),
            ),
            vendido_total=Coalesce(
                Sum("productos__movimientostock__precio_unitario", filter=sales_filter),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            profit_total=Sum("productos__movimientostock__profit_unitario", filter=sales_filter),
            ganancias_desconocidas=Count(
                "productos__movimientostock__movimiento_id",
                filter=sales_filter & Q(productos__movimientostock__profit_unitario__isnull=True),
            ),
        ).annotate(
            # cantidad en ventas suele ser negativa -> la mostramos positiva
            unidades_vendidas=ExpressionWrapper(-F("unidades_raw"), output_field=IntegerField())
        )

        if sort == "ventas":
            qs = qs.order_by("-vendido_total", "nombre")
        elif sort == "productos":
            qs = qs.order_by("-productos_count", "nombre")
        else:
            qs = qs.order_by("nombre")

        return qs


    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["sort"] = (self.request.GET.get("sort") or "nombre").strip().lower()
        return ctx


class MarcaDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = Marca
    template_name = "inventory/marca/marca_detail.html"
    context_object_name = "marca"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        marca = ctx["marca"]

        productos = Producto.objects.filter(marca=marca).order_by("nombre")
        ctx["productos"] = productos

        # Ventas GLOBAL de la marca
        sales_qs = MovimientoStock.objects.filter(
            producto__marca=marca,
            tipo=MovimientoStock.Tipo.VENTA,
        )

        agg = sales_qs.aggregate(
            vendido_total=Coalesce(
                Sum("precio_unitario"),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
            ),
            profit_total=Sum("profit_unitario"),
            ganancias_desconocidas=Count("movimiento_id", filter=Q(profit_unitario__isnull=True)),
            unidades_raw=Coalesce(Sum("cantidad"), Value(0)),
        )

        profit_total = None if agg.get("ganancias_desconocidas") else (agg["profit_total"] or Decimal("0.00"))
        ctx["stats"] = {
            "productos_count": productos.count(),
            "vendido_total": agg["vendido_total"] or Decimal("0.00"),
            "profit_total": profit_total,
            "unidades_vendidas": -int(agg["unidades_raw"] or 0),  # ventas negativas -> positivo
        }
        return ctx

class MarcaCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Marca
    fields = ["nombre"]
    template_name = "inventory/marca/marca_form.html"
    success_url = reverse_lazy("inventory:marca_list")


class MarcaUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Marca
    fields = ["nombre"]
    template_name = "inventory/marca/marca_form.html"

    def get_success_url(self):
        return reverse_lazy("inventory:marca_detail", kwargs={"pk": self.object.pk})


class MarcaDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Marca
    template_name = "inventory/marca/marca_confirm_delete.html"
    success_url = reverse_lazy("inventory:marca_list")