from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.index, name="index"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("productos/", views.ProductoListView.as_view(), name="producto_list"),
    path("productos/nuevo/", views.ProductoCreateView.as_view(), name="producto_create"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto_detail"),
    path("productos/<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_update"),
    path("productos/<int:pk>/borrar/", views.ProductoDeleteView.as_view(), name="producto_delete"),
    path("articulos/", views.articulos, name="articulos"),
]
