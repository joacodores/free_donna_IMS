from decimal import Decimal
from django import forms 
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Local, Producto, Promocion, Venta

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

    def clean_barcode(self):
        barcode = (self.cleaned_data["barcode"] or "").strip()
        if not barcode:
            raise forms.ValidationError("El código de barras es obligatorio.")
        return barcode

# inventory/forms.py
from django import forms
from .models import Articulo

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
    
class PromocionForm(forms.ModelForm):
    class Meta:
        model = Promocion
        fields = [
            "nombre",
            "descripcion",
            "estado",
            "tipo_descuento",
            "valor",
            "fecha_inicio",
            "fecha_fin",
            "prioridad",
            "aplica_a_todos",
            "marcas",
            "productos",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "search-input",
                "placeholder": "Ej: 10% en Adidas",
            }),
            "descripcion": forms.TextInput(attrs={
                "class": "search-input",
                "placeholder": "Descripción breve",
            }),
            "estado": forms.Select(attrs={"class": "select"}),
            "tipo_descuento": forms.Select(attrs={"class": "select"}),
            "valor": forms.NumberInput(attrs={
                "class": "search-input",
                "step": "0.01",
                "min": "0.01",
            }),
            "fecha_inicio": forms.DateTimeInput(attrs={
                "class": "search-input",
                "type": "datetime-local",
            }),
            "fecha_fin": forms.DateTimeInput(attrs={
                "class": "search-input",
                "type": "datetime-local",
            }),
            "prioridad": forms.NumberInput(attrs={
                "class": "search-input",
                "min": "0",
            }),
            "aplica_a_todos": forms.CheckboxInput(attrs={
                "class": "checkbox",
            }),
            "marcas": forms.SelectMultiple(attrs={
                "class": "select",
                "size": "8",
            }),
            "productos": forms.SelectMultiple(attrs={
                "class": "select",
                "size": "10",
            }),
        }

    def clean(self):
        cleaned = super().clean()

        aplica_a_todos = cleaned.get("aplica_a_todos")
        marcas = cleaned.get("marcas")
        productos = cleaned.get("productos")
        tipo = cleaned.get("tipo_descuento")
        valor = cleaned.get("valor")
        inicio = cleaned.get("fecha_inicio")
        fin = cleaned.get("fecha_fin")

        if not aplica_a_todos and not marcas and not productos:
            raise forms.ValidationError(
                "Seleccioná al menos una marca o un producto, o marcá 'Aplica a todo el catálogo'."
            )

        if valor is not None and valor <= 0:
            raise forms.ValidationError("El valor del descuento debe ser mayor a 0.")

        if tipo == Promocion.TipoDescuento.PORCENTAJE and valor and valor > 100:
            raise forms.ValidationError("El porcentaje no puede ser mayor a 100.")

        if inicio and fin and fin < inicio:
            raise forms.ValidationError("La fecha de fin no puede ser anterior a la fecha de inicio.")

        return cleaned