from django.contrib import admin

from .models import Ingreso, IngresoItem, Local, Producto, Articulo, Venta, VentaArticulo, VentaItem

# Register your models here.
admin.site.register(Producto)
admin.site.register(Articulo)
admin.site.register(Venta)
admin.site.register(VentaItem)
admin.site.register(VentaArticulo)
admin.site.register(Ingreso)
admin.site.register(IngresoItem)

@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("local_id", "nombre")
    search_fields = ("nombre",)