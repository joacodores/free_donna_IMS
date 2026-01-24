from django.shortcuts import render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Producto, Articulo

def home(request):
    return render(request, "inventory/base.html")

def productos(request):
    prods = Producto.objects.all()
    return render(request, "inventory/producto_list.html", {"productos": prods})

def articulos(request):
    arts = Articulo.objects.all()
    return render(request, "inventory/articulo_list.html", {"articulos": arts})

class ProductoListView(ListView):
    model = Producto
    template_name = "inventory/producto_list.html"
    context_object_name = "productos"
    paginate_by = 20  # opcional

class ProductoDetailView(DetailView):
    model = Producto
    template_name = "inventory/producto_detail.html"
    context_object_name = "producto"

class ProductoCreateView(CreateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")

class ProductoUpdateView(UpdateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")