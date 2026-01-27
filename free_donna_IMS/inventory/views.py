from django.shortcuts import render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, DeleteView
from django.db.models import Q
from django.shortcuts import redirect
from .models import Producto, Articulo
from .forms import UserLoginForm, UserRegisterForm, ArticuloCreateForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import FormView
from django.db import transaction
from django.contrib import messages

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
        qs = super().get_queryset().select_related("product_id").order_by("sku", "talle", "color", "articulo_id")
        
        scan = (self.request.GET.get("scan") or "").strip()
        if scan:
            return qs.filter(barcode=scan)
        
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
        ctx["field"] = (self.request.GET.get("field") or "all").strip().lower()
        
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
        talle = form.cleaned_data['talle']
        color = form.cleaned_data['color']
        cantidad = form.cleaned_data['cantidad']
        
        articulos = [
            Articulo(
                product_id=producto,
                sku=sku,
                barcode=barcode,
                talle=talle,
                color=color,
            )
            for _ in range(cantidad)
        ]
        Articulo.objects.bulk_create(articulos)
        messages.success(self.request, f"Se cargaron {cantidad} artículo(s) para {producto}.")
        return super().form_valid(form)