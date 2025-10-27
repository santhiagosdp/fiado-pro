# carteira/forms.py
import re
from django import forms
from django.core.exceptions import ValidationError

from django.forms import formset_factory
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cpf", "telefone"]
        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nome do cliente"
            }),
            # Mantém o nome do campo como 'cpf' (model), mas dá o ID que o JS usa: 'id_cpf_cnpj'
            "cpf": forms.TextInput(attrs={
                "class": "form-control",
                "id": "id_cpf_cnpj",
                "placeholder": "CPF ou CNPJ",
                "inputmode": "numeric",
                "autocomplete": "on",
            }),
            "telefone": forms.TextInput(attrs={
                "class": "form-control",
                "id": "id_telefone",
                "placeholder": "(00) 00000-0000",
                "inputmode": "tel",
                "autocomplete": "tel",
                "maxlength": "16",  # suficiente para (00) 00000-0000
            }),
        }

    def clean_cpf(self):
        """
        Aceita CPF (11 dígitos) ou CNPJ (14 dígitos).
        Remove qualquer máscara e retorna apenas números.
        """
        v = self.cleaned_data.get("cpf", "") or ""
        digits = re.sub(r"\D+", "", v)

        if len(digits) not in (11, 14):
            raise ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos) válido.")

        # Se quiser validar dígito verificador de CPF/CNPJ, me avise que adiciono aqui.
        return digits

    def clean_telefone(self):
        """
        Remove máscara. Aceita 10 ou 11 dígitos (fixo ou celular com 9).
        """
        v = self.cleaned_data.get("telefone", "") or ""
        digits = re.sub(r"\D+", "", v)

        if len(digits) not in (10, 11):
            raise ValidationError("Informe um telefone válido (DDD + número).")

        return digits


class ContaForm(forms.ModelForm):
    class Meta:
        model = ContaCarteira
        fields = ["vencimento"]
        widgets = {
            "vencimento": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date"
            }),
        }


class ItemInlineForm(forms.Form):
    produto = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Produto"})
    )
    quantidade = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    valor_unit = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )


ItemFormSet = formset_factory(ItemInlineForm, extra=1, can_delete=True)


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["valor", "observacao"]
        widgets = {
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "observacao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Obs (opcional)"}),
        }


class DeleteConfirmForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo da exclusão",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Informe o motivo"}),
    )
    senha = forms.CharField(
        label="Sua senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirme sua senha"}),
    )


class RestoreConfirmForm(forms.Form):
    senha = forms.CharField(
        label="Sua senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirme sua senha"}),
    )
