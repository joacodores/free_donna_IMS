from django import forms 
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

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
        
        