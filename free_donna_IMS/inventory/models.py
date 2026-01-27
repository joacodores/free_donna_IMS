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

class Articulo(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "DISP", "Disponible"
        VENDIDO = "VEND", "Vendido"
        BAJA = "BAJA", "Baja" # pérdida/rotura/ajuste
        RESERVADO = "RES", "Reservado"
    
    articulo_id = models.AutoField(primary_key=True)
    barcode = models.CharField(max_length=100, db_index=True)
    product_id = models.ForeignKey(Producto, on_delete=models.CASCADE)
    sku = models.CharField(max_length=100)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    estado = models.CharField(max_length=4, choices=Estado.choices, default=Estado.DISPONIBLE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['sku']),  
        ] 

    def __str__(self):
        return f"[{self.articulo_id}] {self.sku}"
    
class MovimientoStock(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "IN", "Entrada"
        SALIDA = "OUT", "Salida"
        AJUSTE = "ADJ", "Ajuste"

    movimiento_id = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=3, choices=Tipo.choices)
    fecha = models.DateTimeField(auto_now_add=True)

    
    articulo = models.ForeignKey("Articulo", on_delete=models.PROTECT, null=True, blank=True)

    # Datos “de lectura rápida” (evita joins en reportes)
    producto = models.ForeignKey("Producto", on_delete=models.PROTECT)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=64)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)

    cantidad = models.IntegerField()  
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)

    referencia = models.CharField(max_length=80, blank=True)  
    nota = models.TextField(blank=True)