# fiado_pro/views_auth.py
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.generic import CreateView
from django.shortcuts import redirect, render
from django.db import transaction
from django.conf import settings

from carteira.models import Empresa
from .forms import SignUpForm


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    # após cadastro, manda pro login com aviso para confirmar e-mail
    success_url = reverse_lazy("login")

    @transaction.atomic
    def form_valid(self, form):
        # salva o User criado pelo formulário (UserCreationForm?)
        response = super().form_valid(form)
        user = self.object

        # 1) garantir que o usuário fique INATIVO até confirmar o e-mail
        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])

        # 2) criar a empresa vinculada (ajuste os nomes dos campos conforme seu form/model)
        Empresa.objects.create(
            owner=user,  # ajuste se seu model usar outro nome de campo
            nome=form.cleaned_data["empresa_nome"],
            cnpj_cpf=form.cleaned_data.get("empresa_cnpj_cpf", ""),
            telefone=form.cleaned_data.get("empresa_telefone", ""),
            endereco=form.cleaned_data.get("empresa_endereco", ""),
        )

        # 3) gerar token e link absoluto de ativação
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse("activate", kwargs={"uidb64": uid, "token": token})
        link_ativacao = self.request.build_absolute_uri(url)

        # 4) montar e enviar o e-mail
        subject = "Ative sua conta - Fiado Pro"
        body = (
            f"Olá {user.get_username()},\n\n"
            f"Ative sua conta clicando no link abaixo:\n{link_ativacao}\n\n"
            f"Se você não solicitou este cadastro, ignore este e-mail."
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        # 5) NÃO autenticar/login aqui — o usuário ainda está inativo
        messages.success(
            self.request,
            "Cadastro realizado! Enviamos um link de ativação para o seu e-mail."
        )
        # ignora 'response' do CreateView e redireciona já com a mensagem
        return redirect(self.success_url)


def activate_account(request, uidb64, token):
    """Confirma o e-mail e ativa a conta."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, TypeError, ValueError, OverflowError):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Conta ativada com sucesso! Faça login.")
        return redirect("login")

    messages.error(request, "Link de ativação inválido ou expirado.")
    return redirect("password_reset")
