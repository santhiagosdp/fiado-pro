# carteira/urls.py
from django.urls import path
from . import views

app_name = "carteira"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clientes/", views.clientes_lista, name="clientes_lista"),
    path("nova/", views.nova_conta, name="nova"),
    path("conta/<int:conta_id>/", views.conta_detalhe, name="conta"),
    path("conta/<int:conta_id>/pagar/", views.pagar, name="pagar"),
    path("conta/<int:conta_id>/recibo/", views.recibo_conta, name="recibo_conta"),
    path("pagamento/<int:pagamento_id>/recibo/", views.recibo_pagamento, name="recibo_pagamento"),
    path("conta/<int:conta_id>/excluir/", views.excluir_conta, name="excluir_conta"),
    path("excluidos/", views.excluidos, name="excluidos"),  # + NEW
    path("conta/<int:conta_id>/restaurar/", views.restaurar_conta, name="restaurar_conta"),
    path("historico/", views.historico, name="historico"),

    #contas testes
    path("teste/", views.seed_contas_fixas, name="seed_contas_fixas"),
]
