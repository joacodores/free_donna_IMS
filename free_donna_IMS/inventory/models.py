from django.db import models

# Create your models here.
class Producto(models.Model):
    product_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    tipo_producto = models.CharField(max_length=100, blank=False)
    material = models.CharField(max_length=100)
    marca = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=10, decimal_places=2)  
    
    def __str__(self):
        return f"[{self.product_id}] {self.nombre} ({self.marca})"

class Local(models.Model):
    local_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre

class Articulo(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "DISP", "Disponible"
        VENDIDO = "VEND", "Vendido"
        BAJA = "BAJA", "Baja" # pérdida/rotura/ajuste
        
    
    articulo_id = models.AutoField(primary_key=True)
    barcode = models.CharField(max_length=100, db_index=True)
    product_id = models.ForeignKey(Producto, on_delete=models.CASCADE)
    sku = models.CharField(max_length=100)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    estado = models.CharField(max_length=4, choices=Estado.choices, default=Estado.DISPONIBLE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    #local = models.ForeignKey(Local, on_delete=models.PROTECT, db_index=True)
    ingreso_item = models.ForeignKey("IngresoItem", on_delete=models.PROTECT, null=True, blank=True) 
    
    class Meta:
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['sku']),  
        ] 

    def __str__(self):
        return f"[{self.articulo_id}] {self.sku}"

class Venta(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = "OPEN", "Abierta"
        CERRADA = "CLOSED", "Cerrada"
        ANULADA = "VOID", "Anulada"
        
    venta_id = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    nota = models.TextField(blank=True)
    
    def __str__(self):
        return f"Venta #{self.venta_id}"
    
class VentaItem(models.Model):
    item_id = models.AutoField(primary_key=True)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="items")
    
    #variante vendida
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=64)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    total_linea = models.DecimalField(max_digits=12, decimal_places=2)
    
class VentaArticulo(models.Model): #unidad exacta vendida
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="unidades")
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, unique=True)


class Ingreso(models.Model):
    ingreso_id = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    
    #local = models.ForeignKey(Local, on_delete=models.PROTECT, db_index=True)
    referencia = models.CharField(max_length=80, blank=True)
    nota = models.TextField(blank=True)
    
    def __str__(self):
        return f"Ingreso #{self.ingreso_id}"
    
class IngresoItem(models.Model):
    item_id = models.AutoField(primary_key=True)
    ingreso = models.ForeignKey(Ingreso, on_delete=models.CASCADE, related_name="items")
    
    producto = models.ForeignKey("Producto", on_delete=models.PROTECT)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=64, db_index=True)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    
    cantidad = models.IntegerField()
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    total_linea = models.DecimalField(max_digits=12, decimal_places=2)
    

    
    
#class MovimientoStock(models.Model):
#    class Tipo(models.TextChoices):
#        ENTRADA = "IN", "Entrada"
#        SALIDA = "OUT", "Salida"
#
#    movimiento_id = models.AutoField(primary_key=True)
#    tipo = models.CharField(max_length=3, choices=Tipo.choices)
#    fecha = models.DateTimeField(auto_now_add=True)
#
#    
#    articulo = models.ForeignKey("Articulo", on_delete=models.PROTECT, null=True, blank=True)
#    venta = models.ForeignKey("Venta", on_delete=models.PROTECT, null=True, blank=True)
#    # Datos “de lectura rápida” (evita joins en reportes)
#    producto = models.ForeignKey("Producto", on_delete=models.PROTECT)
#    sku = models.CharField(max_length=100)
#    barcode = models.CharField(max_length=64)
#    talle = models.IntegerField()
#    color = models.CharField(max_length=50)
#
#    cantidad = models.IntegerField()  
#    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)
#
#    referencia = models.CharField(max_length=80, blank=True)  
#    nota = models.TextField(blank=True)