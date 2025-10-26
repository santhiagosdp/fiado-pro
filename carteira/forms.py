# carteira/forms.py
from django.forms import formset_factory
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento
from django import forms



class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cpf", "telefone"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nome do cliente"}),
            "cpf": forms.TextInput(attrs={"class": "form-control", "placeholder": "000.000.000-00"}),
            "telefone": forms.TextInput(attrs={"class": "form-control", "placeholder": "(63) 9 0000-0000"}),
        }


class ContaForm(forms.ModelForm):
    class Meta:
        model = ContaCarteira
        fields = ["vencimento"]
        widgets = {
            "vencimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class ItemInlineForm(forms.Form):
    produto = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Produto"}))
    quantidade = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={"class": "form-control"}))
    valor_unit = forms.DecimalField(min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))


ItemFormSet = formset_factory(ItemInlineForm, extra=1, can_delete=True)


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["valor", "observacao"]
        widgets = {
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "observacao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Obs (opcional)"}),
        }


# carteira/forms.py
# ... imports existentes ...

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

# carteira/forms.py
class RestoreConfirmForm(forms.Form):
    senha = forms.CharField(
        label="Sua senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirme sua senha"}),
    )
