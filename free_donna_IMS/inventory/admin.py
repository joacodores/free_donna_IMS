from django.contrib import admin

from .models import Local, Producto, Articulo

# Register your models here.
admin.site.register(Producto)
admin.site.register(Articulo)

@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("local_id", "nombre")
    search_fields = ("nombre",)