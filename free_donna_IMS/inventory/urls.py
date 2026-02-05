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
    path("set-local/", views.SetLocalView.as_view(), name="set_local"),
    path("articulos/", views.ArticuloListView.as_view(), name="articulo_list"),
    path("articulos/nuevo/", views.ArticuloCreateView.as_view(), name="articulo_create"),
    path("articulos/<int:articulo_id>/editar/", views.ArticuloUpdateView.as_view(), name="articulo_edit"),
    path("articulos/<int:articulo_id>/borrar/", views.ArticuloDeleteView.as_view(), name="articulo_delete"),
    path("pos/", views.POSView.as_view(), name="pos"),
    path("pos/add/", views.POSAddItemByBarcodeView.as_view(), name="pos_add"),
    path("pos/remove/", views.POSRemoveItemView.as_view(), name="pos_remove"),
    path("pos/clear/", views.POSClearView.as_view(), name="pos_clear"),
    path("pos/checkout/", views.POSCheckoutView.as_view(), name="pos_checkout"),
]
