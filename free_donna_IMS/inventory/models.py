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
