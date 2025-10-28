from django.contrib import admin
from django.urls import path, include
from fiado_pro.views_auth import SignUpView, activate_account

urlpatterns = [
    path("admin/", admin.site.urls),

    # cadastro + ativação
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("accounts/ativar/<uidb64>/<token>/", activate_account, name="activate"),

    # rotas padrão de auth (login, logout, reset de senha, etc.)
    path("accounts/", include("django.contrib.auth.urls")),

    # seu app
    path("", include(("carteira.urls", "carteira"), namespace="carteira")),
]
