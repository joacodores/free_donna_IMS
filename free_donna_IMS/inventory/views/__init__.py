"""
Módulo de vistas de inventory reorganizado por temática.
"""

# Utilidades y mixins
from .utilidades import StaffRequiredMixin

# Autenticación (desde authview)
from .authview import SignUpView, LoginView, LogoutView

# Marcas (desde marcasview)
from .marcasview import (
    MarcaListView,
    MarcaDetailView,
    MarcaCreateView,
    MarcaUpdateView,
    MarcaDeleteView,
)

# Productos
from .productos import (
    ProductoListView,
    ProductoDetailView,
    ProductoCreateView,
    ProductoUpdateView,
    ProductoDeleteView,
    ProductoImportXlsxView,
    SetLocalView,
)

# Artículos
from .articulos import (
    ArticuloListView,
    ArticuloCreateView,
    ArticuloUpdateView,
    ArticulosBulkEditView,
    ArticuloBajaView,
    ArticulosBulkBajaView,
    ArticuloLookupByBarcodeView,
    ArticuloImportXlsxView,
)

# POS
from .pos import (
    POSView,
    POSCajaView,
    POSAddItemByBarcodeView,
    POSRemoveItemView,
    POSClearView,
    POSCheckoutView,
    POSDevolucionStartView,
    POSDevolucionCancelView,
    POSDevolucionSetReturnedView,
)

# Movimientos
from .movimientos import (
    MovimientoStockView,
)

# Detalles
from .detalles import (
    VentaDetailView,
    IngresoDetailView,
    BajaDetailView,
)

# Reportes y PDFs
from .reportes import (
    venta_pdf,
    movimiento_pdf,
    pos_resumen_dia_pdf,
    pos_resumen_dia_view,
    pos_resumen_dia_enviar_view,
    ingreso_pdf,
)

# Transferencias
from .transferencias import (
    ArticulosTransferirView,
    TransferenciaDetailView,
)

# Promociones
from .promociones import (
    PromocionListView,
    PromocionCreateView,
    PromocionDetailView,
    PromocionUpdateView,
    PromocionToggleEstadoView,
    PromocionDeleteView,
    ProductoBulkAdjustPreviewView,
    ProductoBulkAdjustApplyView,
    ProductoBulkAdjustUndoView,
    get_promociones_activas,
    get_mejor_promocion_para_producto,
    promocion_aplica_a_producto,
    calcular_precio_con_promocion,
)

__all__ = [
    # Mixins
    'StaffRequiredMixin',
    
    # Auth
    'SignUpView',
    'LoginView',
    'LogoutView',
    
    # Marcas
    'MarcaListView',
    'MarcaDetailView',
    'MarcaCreateView',
    'MarcaUpdateView',
    'MarcaDeleteView',
    
    # Productos
    'ProductoListView',
    'ProductoDetailView',
    'ProductoCreateView',
    'ProductoUpdateView',
    'ProductoDeleteView',
    'ProductoImportXlsxView',
    'SetLocalView',
    
    # Artículos
    'ArticuloListView',
    'ArticuloCreateView',
    'ArticuloUpdateView',
    'ArticulosBulkEditView',
    'ArticuloBajaView',
    'ArticulosBulkBajaView',
    'ArticuloLookupByBarcodeView',
    'ArticuloImportXlsxView',
    
    # POS
    'POSView',
    'POSCajaView',
    'POSAddItemByBarcodeView',
    'POSRemoveItemView',
    'POSClearView',
    'POSCheckoutView',
    'POSDevolucionStartView',
    'POSDevolucionCancelView',
    'POSDevolucionSetReturnedView',
    
    # Movimientos
    'MovimientoStockView',
    
    # Detalles
    'VentaDetailView',
    'IngresoDetailView',
    'BajaDetailView',
    
    # Reportes
    'venta_pdf',
    'movimiento_pdf',
    'pos_resumen_dia_pdf',
    'pos_resumen_dia_view',
    'pos_resumen_dia_enviar_view',
    'ingreso_pdf',
    
    # Transferencias
    'ArticulosTransferirView',
    'TransferenciaDetailView',
    
    # Promociones
    'PromocionListView',
    'PromocionCreateView',
    'PromocionDetailView',
    'PromocionUpdateView',
    'PromocionToggleEstadoView',
    'PromocionDeleteView',
    'ProductoBulkAdjustPreviewView',
    'ProductoBulkAdjustApplyView',
    'ProductoBulkAdjustUndoView',
    'get_promociones_activas',
    'get_mejor_promocion_para_producto',
    'promocion_aplica_a_producto',
    'calcular_precio_con_promocion',
]
