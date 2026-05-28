from ..models import BajaStock, Ingreso, IngresoItem, Local, Marca, MovimientoStock, Producto, Articulo, ProductoBulkAdjust, ProductoBulkAdjustItem, Promocion, RetiroCaja, Transferencia, TransferenciaItem, Venta, VentaItem, VentaArticulo
from ..forms import ArticuloEditForm, ArticuloImportXlsxForm, CheckoutForm, ProductoImportXlsxForm, PromocionForm, TransferirArticuloForm, UserLoginForm, UserRegisterForm, ArticuloCreateForm, ArticuloImportXlsxForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .utilidades import _get_local_activo, _saldo_caja_local
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View
from decimal import Decimal


@login_required
def index(request):
    local = _get_local_activo(request)
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

    ventas_hoy = list(
        ventas_qs.values("venta_id", "fecha", "metodo_de_pago", "total")[:8]
    )

    caja_qs = (
        RetiroCaja.objects
        .filter(
            local=local if local else None,
            fecha=hoy,
        )
        .select_related("usuario")
        .order_by("-fecha")
    )

    if not request.user.is_staff:
        caja_qs = caja_qs.filter(usuario=request.user)

    movimientos_caja = list(caja_qs[:8])

    promociones_activas = Promocion.objects.filter(estado="ACT").count()
    total_en_efectivo = _saldo_caja_local(local) if local else Decimal("0.00")

    context = {
        "now": timezone.now(),
        "local_activo_id": getattr(local, "local_id", None),

        "ventas_hoy_count": agg["ventas_hoy_count"] or 0,
        "ventas_hoy_total": agg["ventas_hoy_total"] or Decimal("0.00"),
        "efectivo_en_caja": total_en_efectivo,
        "promociones_activas": promociones_activas,

        "ventas_hoy": ventas_hoy,
        "movimientos_caja": movimientos_caja,
    }
    return render(request, "inventory/index.html", context)

def _is_admin(user):
    return user.is_staff or user.is_superuser


class SignUpView(View):
    def get(self, request):
        form = UserRegisterForm()
        return render(request, "inventory/auth/signup.html", {"form": form})

    def post(self, request):
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(username=form.cleaned_data['username'],
                                password=form.cleaned_data['password1'])
            login(request, user)
            return redirect("inventory:producto_list")
        return render(request, "inventory/auth/signup.html", {"form": form})

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("inventory:producto_list")
        form = UserLoginForm()
        return render(request, "inventory/auth/login.html", {"form": form})
    
    def post(self, request):
        form = UserLoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request, 
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'])
            if user is not None:
                login(request, user)
                return redirect("inventory:producto_list")
            else:
                form.add_error(None, "Credenciales inválidas")
        return render(request, "inventory/auth/login.html", {"form": form})
    
class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("inventory:login")


