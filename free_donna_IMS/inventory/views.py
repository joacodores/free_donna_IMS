from decimal import Decimal
from django.shortcuts import render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, DeleteView
from django.db.models import Q, Count
from django.shortcuts import redirect
from .models import Producto, Articulo, Venta, VentaItem, VentaArticulo
from .forms import UserLoginForm, UserRegisterForm, ArticuloCreateForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import FormView
from django.db import transaction
from django.contrib import messages
from datetime import datetime as Datetime


@login_required
def index(request):
    return render(request, "inventory/index.html")

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


class ProductoListView(LoginRequiredMixin, ListView):
    model = Producto
    template_name = "inventory/producto/producto_list.html"
    context_object_name = "productos"
    paginate_by = 20  
    
    def get_queryset(self):
        qs = super().get_queryset().order_by("product_id")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(nombre__icontains=q)
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        return ctx  

class ProductoDetailView(DetailView):
    model = Producto
    template_name = "inventory/producto_detail.html"
    context_object_name = "producto"
    
class ProductoCreateView(LoginRequiredMixin, CreateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")


class ProductoUpdateView(LoginRequiredMixin, UpdateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")


class ProductoDeleteView(LoginRequiredMixin, View):
    model = Producto
    template_name = "inventory/producto/producto_confirm_delete.html"
    success_url = reverse_lazy("inventory:producto_list")
    
    def post(self, request, pk):
        producto = Producto.objects.get(pk=pk)
        producto.delete()
        return redirect(self.success_url)

class ArticuloUpdateView(LoginRequiredMixin, UpdateView):
    model = Articulo
    fields = ["product_id", "sku", "talle", "color"]
    context_object_name = "articulo"
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo/articulo_form.html"
    
    def get_success_url(self):
        return reverse_lazy("inventory:articulo_list")
    
class ArticuloDeleteView(LoginRequiredMixin, DeleteView):
    model = Articulo
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo_confirm_delete.html"
    success_url = reverse_lazy("inventory:articulo_list")
    
class ArticuloListView(LoginRequiredMixin, ListView):
    model = Articulo
    template_name = "inventory/articulo/articulo_list.html"
    context_object_name = "articulos"
    paginate_by = 20
    
    def get_queryset(self):
        qs = super().get_queryset().select_related("product_id")
        estado = (self.request.GET.get("estado") or "DISP").strip().upper()
        if estado in ["DISP", "VEND", "BAJA"]:
            qs = qs.filter(estado=estado)
        qs = qs.order_by("created_at", "articulo_id")
        
        scan = (self.request.GET.get("scan") or "").strip()
        if scan:
            return qs.filter(barcode=scan, estado="DISP")
        
        q = (self.request.GET.get("q") or "").strip()
        field = (self.request.GET.get("field") or "all").strip().lower()
        
        if field not in ["all", "sku", "producto", "color", "talle", "nombre", "marca"]:
            field = "all"
        if not q:
            return qs
        if field == "all":
            filt = (
                Q(sku__icontains=q) |
                Q(color__icontains=q) |
                Q(barcode__icontains=q) |
                Q(product_id__nombre__icontains=q) |
                Q(product_id__marca__icontains=q)
            )
            if q.isdigit():
                n = int(q)
                filt |= Q(talle=n) | Q(articulo_id=n)
                return qs.filter(filt)
        if field == "sku":
            return qs.filter(sku__icontains=q)
        if field == "producto":
            return qs.filter(product_id__nombre__icontains=q)
        if field == "marca":
            return qs.filter(product_id__marca__icontains=q)
        if field == "color":
            return qs.filter(color__icontains=q)
        if field == "talle":
            return qs.filter(talle=int(q)) if q.isdigit() else qs.none()
        if field == "id":
            return qs.filter(articulo_id=int(q)) if q.isdigit() else qs.none()
        
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["scan"] = (self.request.GET.get("scan") or "").strip()
        ctx["q"] = (self.request.GET.get("q") or "").strip()

        field = (self.request.GET.get("field") or "all").strip().lower()
        if field not in ["all", "sku", "producto", "marca", "color", "talle", "id", "barcode"]:
            field = "all"
        ctx["field"] = field
        ctx["estado"] = (self.request.GET.get("estado") or "DISP").upper()
        ctx["auto_open_first"] = bool(ctx["scan"] and ctx["articulos"])
        return ctx
    
    

class ArticuloCreateView(LoginRequiredMixin, FormView):
    template_name = "inventory/articulo/articulo_create.html"
    form_class = ArticuloCreateForm
    success_url = reverse_lazy("inventory:articulo_list")
    
    @transaction.atomic
    def form_valid(self, form):
        producto = form.cleaned_data['product_id']
        sku = form.cleaned_data['sku']
        barcode = form.cleaned_data['barcode']
        created_at = Datetime.now()
        talle = form.cleaned_data['talle']
        color = form.cleaned_data['color']
        cantidad = form.cleaned_data['cantidad']
        
        articulos = [
            Articulo(
                product_id=producto,
                sku=sku,
                barcode=barcode,
                created_at=created_at,
                estado=Articulo.Estado.DISPONIBLE,
                talle=talle,
                color=color,
            )
            for _ in range(cantidad)
        ]
        Articulo.objects.bulk_create(articulos)
        messages.success(self.request, f"Se cargaron {cantidad} artículo(s) para {producto}.")
        return super().form_valid(form)
    

CART_KEY = "pos_cart"

def _get_cart(session):
    return session.get(CART_KEY, {})

def _save_cart(session, cart):
    session[CART_KEY] = cart
    session.modified = True
    
def _cart_totals(cart):
    subtotal = Decimal("0.00")
    for it in cart.values():
        line_total = Decimal(it["precio"]) * int(it["qty"])
        it["line_total"] = str(line_total)  # guardo string para render simple
        subtotal += line_total
    return subtotal, subtotal

class POSView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos.html"
    def get(self, request):
        cart = _get_cart(request.session)
        barcodes = [it["barcode"] for it in cart.values()]
        stock_map = {}
        if barcodes:
            rows = (Articulo.objects
                    .filter(barcode__in=barcodes, estado=Articulo.Estado.DISPONIBLE)
                    .values("barcode")
                    .annotate(disponibles=Count("articulo_id"))
                    )
            stock_map = {r["barcode"]: r["disponibles"] for r in rows}
        subtotal, total = _cart_totals(cart)
        return render(request, self.template_name, {
            "cart": cart,
            "stock_map": stock_map,
            "subtotal": subtotal,
            "total": total,
        })    
        
class POSAddItemByBarcodeView(LoginRequiredMixin, View):
    def post(self, request):
        barcode = (request.POST.get("barcode") or "").strip()
        if not barcode:
            messages.error(request, "Escaneá un código de barras.")
            return redirect("inventory:pos")
        art = (Articulo.objects
                .select_related("product_id")
                .filter(barcode=barcode)
                .order_by("articulo_id")
                .first())
        if not art:
            messages.error(request, f"No existe ningún artículo cargado con código de barras {barcode}.")
            return redirect("inventory:pos")
        
        disponibles = Articulo.objects.filter(barcode=barcode, estado=Articulo.Estado.DISPONIBLE).count()
        if disponibles <= 0:
            messages.error(request, f"No hay unidades disponibles para el artículo '{art.product_id.nombre}' (Código de barras: {barcode}).")
            return redirect("inventory:pos")
        
        line_key = f"{barcode}|{art.talle}|{art.color}"
        cart = _get_cart(request.session)
        if line_key not in cart:
            precio=getattr(art.product_id, "precio", None)
            if precio is None:
                messages.error(request, f"El producto '{art.product_id.nombre}' no tiene un precio definido.")
                return redirect("inventory:pos")
            cart[line_key] = {
                "producto_id": art.product_id.product_id,
                "producto_nombre": getattr(art.product_id, "nombre", ""),
                "marca": getattr(art.product_id, "marca", ""),
                "sku": art.sku,
                "barcode": art.barcode,
                "talle": art.talle,
                "color": art.color,
                "precio": str(precio),
                "qty": 1,
            }
        else:
            new_qty = int(cart[line_key]["qty"]) + 1
            if new_qty > disponibles:
                messages.error(request, f"No hay stock suficiente. Disponibles: {disponibles}.")
                return redirect("inventory:pos")
            cart[line_key]["qty"] = new_qty
            
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
    def post(self, request):
        _save_cart(request.session, {})
        return redirect("inventory:pos")
    
class POSCheckoutView(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request):
        cart = _get_cart(request.session)
        if not cart:
            messages.error(request, "El carrito está vacío.")
            return redirect("inventory:pos")

        venta = Venta.objects.create(usuario=request.user, estado=Venta.Estado.ABIERTA)

        subtotal = Decimal("0.00")

        
        for key, it in cart.items():
            barcode = it["barcode"]
            qty = int(it["qty"])
            precio = Decimal(it["precio"])

            disponibles_qs = (Articulo.objects
                              .select_for_update()
                              .filter(barcode=barcode, estado=Articulo.Estado.DISPONIBLE)
                              .order_by("articulo_id"))
            articulos = list(disponibles_qs[:qty])
            if len(articulos) < qty:
                raise ValueError(f"Stock insuficiente para barcode {barcode}. Pediste {qty}, hay {len(articulos)}.")


            total_linea = precio * qty
            subtotal += total_linea

            item = VentaItem.objects.create(
                venta=venta,
                producto_id=it["producto_id"],
                sku=it["sku"],
                barcode=barcode,
                talle=int(it["talle"]),
                color=it["color"],
                cantidad=qty,
                precio_unitario=precio,
                total_linea=total_linea,
            )

            # Marcar unidades como vendidas 
            Articulo.objects.filter(articulo_id__in=[a.articulo_id for a in articulos]).update(
                estado=Articulo.Estado.VENDIDO
            )

            # Registrar unidades vendidas 
            VentaArticulo.objects.bulk_create([
                VentaArticulo(venta=venta, articulo=a) for a in articulos
            ])

        #Cerrar venta 
        venta.subtotal = subtotal
        venta.total = subtotal
        venta.estado = Venta.Estado.CERRADA
        venta.save(update_fields=["subtotal", "total", "estado"])

        
        _save_cart(request.session, {})

        messages.success(request, f"Venta #{venta.venta_id} cerrada. Total: $ {venta.total}")
        return redirect("inventory:pos")
    
        