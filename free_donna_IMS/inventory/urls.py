from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.home, name="index"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("productos/", views.productos, name="producto_list"),
    path("articulos/", views.articulos, name="articulos"),
    path("productos/nuevo/", views.ProductoCreateView.as_view(), name="producto_create"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto_detail"),
    path("productos/<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_update"),
]
