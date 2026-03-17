from decimal import Decimal
from django import forms 
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Local, Producto, Promocion, Venta, Articulo, RetiroCaja

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        

class UserLoginForm(forms.Form):
    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(attrs={
            "class": "auth-input",
            "placeholder": "Usuario"
        })
    )

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={
            "class": "auth-input",
            "placeholder": "Contraseña"
        })
    )
        
class ArticuloCreateForm(forms.Form):
    product_id = forms.ModelChoiceField(
        queryset=Producto.objects.all(),
        label="Producto"
    )
    sku_preview = forms.CharField(
        required=False,
        max_length=80,
        widget=forms.TextInput(attrs={"readonly": "readonly"})
    )
    barcode = forms.CharField(max_length=64, label="Barcode")
    talle = forms.IntegerField(min_value=1, label="Talle")
    color = forms.CharField(max_length=50, label="Color")
    cantidad = forms.IntegerField(min_value=1, max_value=500, initial=1, label="Cantidad")
    referencia = forms.CharField(max_length=80, required=False, label="Referencia")

    def __init__(self, *args, **kwargs):
        self.local = kwargs.pop("local", None)
        super().__init__(*args, **kwargs)

    def clean_barcode(self):
        barcode = (self.cleaned_data["barcode"] or "").strip()
        if not barcode:
            raise forms.ValidationError("El código de barras es obligatorio.")
        return barcode

    def clean_color(self):
        color = (self.cleaned_data["color"] or "").strip()
        if not color:
            raise forms.ValidationError("El color es obligatorio.")
        return color

    def clean(self):
        cleaned = super().clean()

        barcode = (cleaned.get("barcode") or "").strip()
        producto = cleaned.get("product_id")
        talle = cleaned.get("talle")
        color = (cleaned.get("color") or "").strip()

        if not barcode or not producto or talle is None or not color:
            return cleaned

        qs = Articulo.objects.select_related("product_id").filter(barcode=barcode)

        if self.local:
            qs = qs.filter(local=self.local)

        existente = qs.order_by("-articulo_id").first()

        if existente:
            errores = {}

            if existente.product_id_id != producto.pk:
                errores["product_id"] = "Ese barcode ya está asociado a otro producto."

            if existente.talle != talle:
                errores["talle"] = "Ese barcode ya está asociado a otro talle."

            if (existente.color or "").strip().lower() != color.lower():
                errores["color"] = "Ese barcode ya está asociado a otro color."

            if errores:
                raise forms.ValidationError(errores)

        return cleaned


class ArticuloEditForm(forms.ModelForm):
    bulk = False

    class Meta:
        model = Articulo
        fields = ["barcode", "product_id", "sku", "talle", "color"]
        widgets = {
            "barcode": forms.TextInput(attrs={"class": "search-input"}),
            "product_id": forms.Select(attrs={"class": "select"}),
            "sku": forms.TextInput(attrs={"class": "search-input"}),
            "talle": forms.TextInput(attrs={"class": "search-input"}),
            "color": forms.TextInput(attrs={"class": "search-input"}),
        }

    def __init__(self, *args, bulk=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.bulk = bulk
        if bulk:
            for f in self.fields.values():
                f.required = False
            self.fields["product_id"].empty_label = "— No cambiar —"
            for name, f in self.fields.items():
                f.help_text = None

    def clean(self):
        cd = super().clean()
        if self.bulk:
            if not any(cd.get(k) not in (None, "", []) for k in self.fields.keys()):
                raise forms.ValidationError("Ingresá al menos un cambio.")
        return cd

class CheckoutForm(forms.Form):
    metodo_pago = forms.ChoiceField(
        choices=Venta.MetodoPago.choices,
        initial=Venta.MetodoPago.EFECTIVO,
        label="Método de pago",
        widget=forms.Select(attrs={"class": "select"})
    )

class TransferirArticuloForm(forms.Form):
    destino = forms.ModelChoiceField(queryset=Local.objects.all(), empty_label="Seleccionar local")
    nota = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

class ArticuloImportXlsxForm(forms.Form):
    file = forms.FileField(label="Excel (.xlsx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith(".xlsx"):
            raise forms.ValidationError("Subí un archivo .xlsx")
        return f
    
from django import forms
from .models import Promocion

class PromocionForm(forms.ModelForm):
    class Meta:
        model = Promocion
        fields = [
            "nombre",
            "descripcion",
            "estado",
            "tipo_descuento",
            "valor",
            "descuento_porcentaje",
            "unidad_objetivo",
            "fecha_inicio",
            "fecha_fin",
            "prioridad",
            "aplica_a_todos",
            "marcas",
            "productos",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "search-input"}),
            "descripcion": forms.TextInput(attrs={"class": "search-input"}),
            "estado": forms.Select(attrs={"class": "select"}),
            "tipo_descuento": forms.Select(attrs={"class": "select"}),
            "valor": forms.NumberInput(attrs={"class": "search-input", "step": "0.01", "min": "0"}),
            "descuento_porcentaje": forms.NumberInput(attrs={"class": "search-input", "step": "0.01", "min": "0", "max": "100"}),
            "unidad_objetivo": forms.NumberInput(attrs={"class": "search-input", "min": "2"}),
            "fecha_inicio": forms.DateTimeInput(attrs={"class": "search-input", "type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"class": "search-input", "type": "datetime-local"}),
            "prioridad": forms.NumberInput(attrs={"class": "search-input", "min": "0"}),
            "aplica_a_todos": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "marcas": forms.SelectMultiple(attrs={
                "id": "id_marcas",
                "class": "native-multi-select",
            }),
            "productos": forms.SelectMultiple(attrs={
                "id": "id_productos",
                "class": "native-multi-select",
            }),
        }   

    def clean(self):
        cleaned = super().clean()

        tipo = cleaned.get("tipo_descuento")
        valor = cleaned.get("valor")
        descuento_porcentaje = cleaned.get("descuento_porcentaje")
        unidad_objetivo = cleaned.get("unidad_objetivo")

        aplica_a_todos = cleaned.get("aplica_a_todos")
        marcas = cleaned.get("marcas")
        productos = cleaned.get("productos")

        fecha_inicio = cleaned.get("fecha_inicio")
        fecha_fin = cleaned.get("fecha_fin")

        if not aplica_a_todos and not marcas and not productos:
            raise forms.ValidationError(
                "Seleccioná al menos una marca o un producto, o marcá 'Aplica a todo el catálogo'."
            )

        if tipo == Promocion.TipoDescuento.PORCENTAJE:
            if valor is None or valor <= 0 or valor > 100:
                self.add_error("valor", "Ingresá un porcentaje entre 1 y 100.")
            cleaned["descuento_porcentaje"] = None
            cleaned["unidad_objetivo"] = None

        elif tipo == Promocion.TipoDescuento.MONTO_FIJO:
            if valor is None or valor <= 0:
                self.add_error("valor", "Ingresá un monto mayor a 0.")
            cleaned["descuento_porcentaje"] = None
            cleaned["unidad_objetivo"] = None

        elif tipo == Promocion.TipoDescuento.ESCALON:
            cleaned["valor"] = None

            if unidad_objetivo is None or unidad_objetivo < 2:
                self.add_error("unidad_objetivo", "La unidad objetivo debe ser 2 o mayor.")

            if descuento_porcentaje is None or descuento_porcentaje <= 0 or descuento_porcentaje > 100:
                self.add_error("descuento_porcentaje", "Ingresá un porcentaje entre 1 y 100.")

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error("fecha_fin", "La fecha de fin no puede ser anterior a la fecha de inicio.")

        return cleaned
    
    
    

class ProductoImportXlsxForm(forms.Form):
    file = forms.FileField(
        label="Archivo Excel",
        help_text="Subí un archivo .xlsx con columnas: nombre, tipo_producto, material, marca, precio, costo"
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("El archivo debe ser .xlsx")
        return f