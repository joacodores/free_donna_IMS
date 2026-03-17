from django.conf import settings
from django.db import models
from django.utils import timezone
from decimal import Decimal

# Create your models here.
class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        super().save(*args, **kwargs)
    class Meta:
        ordering = ["nombre"]
    def __str__(self):
        return self.nombre

class Producto(models.Model):
    product_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    tipo_producto = models.CharField(max_length=100, blank=False)
    material = models.CharField(max_length=100)
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="productos")
    precio = models.DecimalField(max_digits=10, decimal_places=2)  
    costo = models.DecimalField(max_digits=10, decimal_places=2)
    
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
    local = models.ForeignKey(Local, null=True, blank=True, on_delete=models.PROTECT, db_index=True)
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
    
    class MetodoPago(models.TextChoices):
        EFECTIVO = "EFEC", "Efectivo"
        TARJETA = "TARJ", "Tarjeta"
        TRANSFERENCIA = "TRANS", "Transferencia"
        OTRO = "OTRO", "Otro"
        
    venta_id = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    nota = models.TextField(blank=True)
    total_descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    local = models.ForeignKey(Local, null=True, blank=True, on_delete=models.PROTECT)
    metodo_de_pago = models.CharField(max_length=15, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO, db_index=True)
    profit_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
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
    promocion = models.ForeignKey("Promocion", null=True, blank=True, on_delete=models.SET_NULL)
    promocion_nombre = models.CharField(max_length=120, blank=True, default="") 
    
    cantidad = models.IntegerField()
    precio_base_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit_linea = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_linea = models.DecimalField(max_digits=12, decimal_places=2)
    
class VentaArticulo(models.Model): #unidad exacta vendida
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="unidades")
    articulo = models.OneToOneField(Articulo, on_delete=models.PROTECT, unique=True)


class Ingreso(models.Model):
    ingreso_id = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    
    local = models.ForeignKey(Local, null=True, blank=True, on_delete=models.PROTECT, db_index=True)
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
    
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad = models.IntegerField()
    total_linea = models.DecimalField(max_digits=12, decimal_places=2)
    
class Transferencia(models.Model):
    transferencia_id = models.BigAutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    local_origen = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="transferencias_salientes", db_index=True)
    local_destino = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="transferencias_entrantes", db_index=True)

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    nota = models.TextField(blank=True)

class TransferenciaItem(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE, related_name="items")
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, db_index=True)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    
class BajaStock(models.Model):
    baja_id = models.BigAutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    local = models.ForeignKey(Local, on_delete=models.PROTECT, db_index=True)
    nota = models.TextField(blank=True)

    def __str__(self):
        return f"Baja #{self.baja_id}"
class MovimientoStock(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "IN", "Ingreso"
        VENTA = "OUT", "Venta"
        TRANSFERENCIA = "TRF", "Transferencia"
        BAJA = "BAJ", "Baja"
        DEVOLUCION = "RET", "Devolución"

    movimiento_id = models.BigAutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True,db_index=True)
    tipo = models.CharField(max_length=3, choices=Tipo.choices, db_index=True)

    local = models.ForeignKey(Local, on_delete=models.PROTECT, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name="movimientos")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    sku = models.CharField(max_length=100, db_index=True)
    barcode = models.CharField(max_length=100, db_index=True)
    talle = models.IntegerField()
    color = models.CharField(max_length=50)
    
    cantidad = models.IntegerField()
    
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    profit_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    ingreso = models.ForeignKey(Ingreso, null=True, blank=True, on_delete=models.PROTECT)
    venta = models.ForeignKey(Venta, null=True, blank=True, on_delete=models.PROTECT)
    transferencia = models.ForeignKey(Transferencia, null=True, blank=True, on_delete=models.PROTECT, db_index=True)
    baja = models.ForeignKey(BajaStock, null=True, blank=True, on_delete=models.PROTECT, db_index=True)
    local_origen = models.ForeignKey(Local, null=True, blank=True, on_delete=models.PROTECT, related_name="movs_origen")
    local_destino = models.ForeignKey(Local, null=True, blank=True, on_delete=models.PROTECT, related_name="movs_destino")
    nota = models.TextField(blank=True)
    
    class Meta:
        ordering = ["-fecha", "-movimiento_id"]
        indexes = [
            models.Index(fields=["local", "fecha"]),
            models.Index(fields=["tipo", "fecha"]),
            models.Index(fields=["barcode"]),
            models.Index(fields=["producto"]),
            models.Index(fields=["venta"]),
            models.Index(fields=["ingreso"]),
        ]
    def __str__(self):
        return f"{self.get_tipo_display()} {self.movimiento_id}"
    

class RetiroCaja(models.Model):
    class Tipo(models.TextChoices):
        SALIDA = "SALIDA", "Salida"
        ENTRADA = "ENTRADA", "Entrada"

    class Motivo(models.TextChoices):
        GUARDAR = "GUARDAR", "Guardar (dueño)"
        GASTO = "GASTO", "Gasto del día"
        APORTE = "APORTE", "Aporte de caja"
        AJUSTE = "AJUSTE", "Ajuste"
        OTRO = "OTRO", "Otro"

    retiro_id = models.BigAutoField(primary_key=True)

    local = models.ForeignKey(
        "inventory.Local",
        on_delete=models.PROTECT,
        related_name="retiros_caja"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="retiros_caja"
    )

    fecha = models.DateField(default=timezone.localdate, db_index=True)

    tipo = models.CharField(
        max_length=10,
        choices=Tipo.choices,
        default=Tipo.SALIDA,
        db_index=True,
    )

    monto = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=16, choices=Motivo.choices, default=Motivo.GUARDAR)
    nota = models.CharField(max_length=140, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["local", "fecha"]),
            models.Index(fields=["local", "tipo"]),
        ]
        ordering = ["-creado_en"]

    def clean(self):
        super().clean()
        if self.monto is not None and self.monto <= Decimal("0.00"):
            raise ValueError("El monto debe ser mayor a 0.")
        
class ProductoBulkAdjust(models.Model):
    class Estado(models.TextChoices):
        APLICADO = "APLICADO"
        DESHECHO = "DESHECHO"

    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    marca = models.ForeignKey("Marca", on_delete=models.PROTECT)

    pct_precio = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    pct_costo  = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    afectados = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.APLICADO)

    # para mostrar en UI / auditoría
    note = models.CharField(max_length=160, blank=True, default="")

    def __str__(self):
        return f"BulkAdjust #{self.pk} - {self.marca} - {self.estado}"


class ProductoBulkAdjustItem(models.Model):
    adjust = models.ForeignKey(ProductoBulkAdjust, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey("Producto", on_delete=models.PROTECT)

    old_precio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    old_costo  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    new_precio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_costo  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = [("adjust", "producto")]
        
class Promocion(models.Model):
    class TipoDescuento(models.TextChoices):
        PORCENTAJE = "PCT", "Porcentaje"
        MONTO_FIJO = "FIX", "Monto fijo"
        ESCALON = "ESC", "Descuento por unidad escalonada" 
    
    class Estado(models.TextChoices):
        ACTIVA = "ACT", "Activa"
        PAUSADA = "PAU", "Pausada"
        
    promocion_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(max_length=255, blank=True)
    
    estado = models.CharField(max_length=3, choices=Estado.choices, default=Estado.ACTIVA)
    tipo_descuento = models.CharField(max_length=3, choices=TipoDescuento.choices)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  
    
    unidad_objetivo = models.PositiveIntegerField(null=True, blank=True)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True) 
    
    prioridad = models.IntegerField(default=0)  
    
    aplica_a_todos = models.BooleanField(default=False)
    
    marcas = models.ManyToManyField("Marca", blank=True, related_name="promociones")
    productos = models.ManyToManyField("Producto", blank=True, related_name="promociones")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.nombre

    def esta_vigente(self):
        ahora = timezone.now()

        if self.estado != self.Estado.ACTIVA:
            return False
        if self.fecha_inicio and ahora < self.fecha_inicio:
            return False
        if self.fecha_fin and ahora > self.fecha_fin:
            return False
        return True
    
    @property
    def alcance_resumen(self):
        if self.aplica_a_todos:
            return "Todo el catálogo"

        marcas = self.marcas.count()
        productos = self.productos.count()

        partes = []
        if marcas:
            partes.append(f"{marcas} marca(s)")
        if productos:
            partes.append(f"{productos} producto(s)")

        return ", ".join(partes) if partes else "—"

