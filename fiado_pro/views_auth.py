# fiado_pro/views_auth.py
from carteira.models import Empresa
from django.db import transaction
from django.contrib.auth import login, authenticate
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import SignUpForm


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('carteira:dashboard')

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object

        # Criar empresa vinculada
        Empresa.objects.create(
            owner=user,
            nome=form.cleaned_data["empresa_nome"],
            cnpj_cpf=form.cleaned_data.get("empresa_cnpj_cpf", ""),
            telefone=form.cleaned_data.get("empresa_telefone", ""),
            endereco=form.cleaned_data.get("empresa_endereco", ""),
        )

        # Autenticar corretamente (sem backend manual)
        username = form.cleaned_data.get("username")
        raw_password = form.cleaned_data.get("password1")
        auth_user = authenticate(self.request, username=username, password=raw_password)
        if auth_user:
            login(self.request, auth_user)

        return response
