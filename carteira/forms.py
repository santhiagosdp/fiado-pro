# carteira/forms.py
import re
from django import forms
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento


class PagamentoForm(forms.ModelForm):
    # Torna opcional no formulário (se vazio, a view usa timezone.now())
    data_pagamento = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"})
    )
    class Meta:
        model = Pagamento
        fields = ["valor", "data_pagamento", "observacao"]
        widgets = {
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "observacao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Obs (opcional)"}),
        }


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cpf", "telefone"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nome do cliente"}),
            "cpf": forms.TextInput(attrs={
                "id": "id_cpf_cnpj", "class": "form-control",
                "placeholder": "000.000.000-00 ou 00.000.000/0000-00",
                "inputmode": "numeric", "autocomplete": "on"}),
            "telefone": forms.TextInput(attrs={
                "id": "id_telefone", "class": "form-control",
                "placeholder": "(63) 9 0000-0000", "inputmode": "tel", "autocomplete": "tel"}),
        }

    def clean_cpf(self):
        v = self.cleaned_data.get("cpf", "") or ""
        digits = re.sub(r"\D+", "", v)
        if len(digits) not in (11, 14):
            raise ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos) válido.")
        return digits

    def clean_telefone(self):
        v = self.cleaned_data.get("telefone", "") or ""
        digits = re.sub(r"\D+", "", v)
        if len(digits) not in (10, 11):
            raise ValidationError("Informe um telefone válido (DDD + número).")
        return digits


class ContaForm(forms.ModelForm):
    class Meta:
        model = ContaCarteira
        fields = ["vencimento"]
        widgets = {"vencimento": forms.DateInput(attrs={"class": "form-control", "type": "date"})}


class ItemInlineForm(forms.Form):
    produto = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Produto"}))
    quantidade = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={"class": "form-control"}))
    valor_unit = forms.DecimalField(min_value=0, decimal_places=2,
                                    widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))


ItemFormSet = formset_factory(ItemInlineForm, extra=1, can_delete=True)


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