# fiado_pro/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from carteira.models import Empresa  # importar o model

User = get_user_model()


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Informe um e-mail válido.")

    # --- CAMPOS DA EMPRESA ---
    empresa_nome = forms.CharField(
        label="Nome da empresa",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Padaria São José"}),
    )
    empresa_cnpj_cpf = forms.CharField(
        label="CNPJ ou CPF",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
    )
    empresa_telefone = forms.CharField(
        label="Telefone",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "(63) 9 9999-9999"}),
    )
    empresa_endereco = forms.CharField(
        label="Endereço",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Rua, número, bairro..."}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email
