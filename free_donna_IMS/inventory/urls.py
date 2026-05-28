from django.urls import path

from .views import authview
from .views import marcasview
from .views.productos import (
    ProductoListView, ProductoDetailView, ProductoCreateView, ProductoUpdateView, ProductoDeleteView,
    ProductoImportXlsxView, SetLocalView
)
from .views.articulos import (
    ArticuloListView, ArticuloCreateView, ArticuloUpdateView, ArticulosBulkEditView,
    ArticuloBajaView, ArticulosBulkBajaView, ArticuloLookupByBarcodeView, ArticuloImportXlsxView
)
from .views.pos import (
    POSView, POSCajaView, POSAddItemByBarcodeView, POSRemoveItemView, POSClearView,
    POSCheckoutView, POSDevolucionStartView, POSDevolucionCancelView, POSDevolucionSetReturnedView
)
from .views.movimientos import MovimientoStockView
from .views.detalles import VentaDetailView, IngresoDetailView, BajaDetailView
from .views.reportes import (
    venta_pdf, movimiento_pdf, ingreso_pdf, pos_resumen_dia_view, pos_resumen_dia_enviar_view
)
from .views.transferencias import ArticulosTransferirView, TransferenciaDetailView
from .views.promociones import (
    PromocionListView, PromocionCreateView, PromocionDetailView, PromocionUpdateView,
    PromocionToggleEstadoView, PromocionDeleteView, ProductoBulkAdjustPreviewView,
    ProductoBulkAdjustApplyView, ProductoBulkAdjustUndoView
)

app_name = "inventory"

urlpatterns = [
    path("", authview.index, name="index"),
    path("signup/", authview.SignUpView.as_view(), name="signup"),
    path("login/", authview.LoginView.as_view(), name="login"),
    path("logout/", authview.LogoutView.as_view(), name="logout"),
    path("marcas/", marcasview.MarcaListView.as_view(), name="marca_list"),
    path("marcas/nueva/", marcasview.MarcaCreateView.as_view(), name="marca_create"),
    path("marcas/<int:pk>/", marcasview.MarcaDetailView.as_view(), name="marca_detail"),
    path("marcas/<int:pk>/editar/", marcasview.MarcaUpdateView.as_view(), name="marca_edit"),
    path("marcas/<int:pk>/borrar/", marcasview.MarcaDeleteView.as_view(), name="marca_delete"),
    path("productos/", ProductoListView.as_view(), name="producto_list"),
    path("productos/nuevo/", ProductoCreateView.as_view(), name="producto_create"),
    path("productos/<int:pk>/", ProductoDetailView.as_view(), name="producto_detail"),
    path("productos/<int:pk>/editar/", ProductoUpdateView.as_view(), name="producto_update"),
    path("productos/<int:pk>/borrar/", ProductoDeleteView.as_view(), name="producto_delete"),
    path("set-local/", SetLocalView.as_view(), name="set_local"),
    path("articulos/", ArticuloListView.as_view(), name="articulo_list"),
    path("articulos/nuevo/", ArticuloCreateView.as_view(), name="articulo_create"),
    path("articulos/lookup/", ArticuloLookupByBarcodeView.as_view(), name="articulo_lookup"),
    path("articulos/<int:articulo_id>/editar/", ArticuloUpdateView.as_view(), name="articulo_edit"),
    path("articulos/<int:articulo_id>/baja/", ArticuloBajaView.as_view(), name="articulo_baja"),
    path("pos/", POSView.as_view(), name="pos"),
    path("pos/retirar-efectivo/", POSCajaView.as_view(), name="pos_caja"),
    path("pos/add/", POSAddItemByBarcodeView.as_view(), name="pos_add"),
    path("pos/remove/", POSRemoveItemView.as_view(), name="pos_remove"),
    path("pos/clear/", POSClearView.as_view(), name="pos_clear"),
    path("pos/checkout/", POSCheckoutView.as_view(), name="pos_checkout"),
    path("movimientos/", MovimientoStockView.as_view(), name="movimientos"),
    path("movimientos/pdf/", movimiento_pdf, name="movimientos_pdf"),
    path("ventas/<int:venta_id>/", VentaDetailView.as_view(), name="venta_detail"),
    path("ventas/<int:venta_id>/pdf/", venta_pdf, name="venta_pdf"),
    path("ingresos/<int:ingreso_id>/", IngresoDetailView.as_view(), name="ingreso_detail"),
    path("ingresos/<int:ingreso_id>/pdf/", ingreso_pdf, name="ingreso_pdf"),
    path("transferencias/<int:transferencia_id>/", TransferenciaDetailView.as_view(), name="transferencia_detail"),
    path("articulos/transferir/", ArticulosTransferirView.as_view(), name="articulos_transferir"),
    path("articulos/import-excel/", ArticuloImportXlsxView.as_view(), name="articulo_import_excel"),
    path("articulos/bulk-edit-form/", ArticulosBulkEditView.as_view(), name="articulo_bulk_edit_form"),
    path("articulos/bulk-baja/", ArticulosBulkBajaView.as_view(), name="articulos_bulk_baja"),
    path("bajas/<int:baja_id>/", BajaDetailView.as_view(), name="baja_detail"),
    path("productos/ajuste-marca/preview/", ProductoBulkAdjustPreviewView.as_view(), name="producto_bulk_marca_preview"),
    path("productos/ajuste-marca/apply/", ProductoBulkAdjustApplyView.as_view(), name="producto_bulk_marca_apply"),
    path("productos/ajuste-marca/undo/<int:adjust_id>/", ProductoBulkAdjustUndoView.as_view(), name="producto_bulk_marca_undo"),
    path("promociones/", PromocionListView.as_view(), name="promocion_list"),
    path("promociones/nueva/", PromocionCreateView.as_view(), name="promocion_create"),
    path("promociones/<int:promocion_id>/", PromocionDetailView.as_view(), name="promocion_detail"),
    path("promociones/<int:promocion_id>/editar/", PromocionUpdateView.as_view(), name="promocion_edit"),
    path("promociones/<int:promocion_id>/toggle/", PromocionToggleEstadoView.as_view(), name="promocion_toggle"),
    path("promociones/<int:promocion_id>/delete/", PromocionDeleteView.as_view(), name="promocion_delete"),
    path("productos/importar-excel/", ProductoImportXlsxView.as_view(), name="producto_import_excel"),
    path("pos/resumen-dia/pdf/", pos_resumen_dia_view, name="pos_resumen_dia"),
    path("pos/resumen-dia/pdf/enviar/", pos_resumen_dia_enviar_view, name="pos_resumen_dia_enviar"),
    path("pos/devolucion/start/", POSDevolucionStartView.as_view(), name="pos_devolucion_start"),
    path("pos/devolucion/cancel/", POSDevolucionCancelView.as_view(), name="pos_devolucion_cancel"),
    path("pos/devolucion/set-returned/", POSDevolucionSetReturnedView.as_view(), name="pos_devolucion_set_returned"),
]
