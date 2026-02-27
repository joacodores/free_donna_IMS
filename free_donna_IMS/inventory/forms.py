from decimal import Decimal
from django import forms 
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Local, Producto, Venta

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