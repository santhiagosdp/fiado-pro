# carteira/models.py
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings

class Empresa(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="empresa")
    nome = models.CharField(max_length=150)
    cnpj_cpf = models.CharField(max_length=20, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    endereco = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.nome}" + (f" — {self.cnpj_cpf}" if self.cnpj_cpf else "") + f"{self.telefone}"

class Cliente(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cliente")
    nome = models.CharField(max_length=150)
    data_nascimento = models.DateField(default=timezone.now)
    cpf = models.CharField(max_length=14, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    endereco = models.CharField(max_length=150, default="endereco aqui")
    email = models.CharField(max_length=150, default="email-do-cliente@mail.com.br")

    def __str__(self):
        return f"{self.nome}" + (f" — {self.cpf}" if self.cpf else "")

class ContaCarteira(models.Model):
    STATUS_CHOICES = (
        ("EM_ABERTO", "Em aberto"),
        ("PAGO", "Pago"),
        ("ATRASO", "Em atraso"),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contas_carteira")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="contas")
    criado_em = models.DateField(default=timezone.now)
    vencimento = models.DateField(null=True, blank=True)

    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="EM_ABERTO")

    # --- SOFT DELETE ---
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_reason = models.CharField(max_length=255, blank=True)
    deleted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contas_carteira_excluidas"
    )

    class Meta:
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"Conta #{self.id} — {self.cliente.nome}"

    def atualizar_totais(self, commit=True):
        itens_total = sum((i.subtotal() for i in self.itens.all()), start=Decimal("0"))
        total_pago = sum((p.valor for p in self.pagamentos.all()), start=Decimal("0"))

        novo_saldo = itens_total - total_pago
        if novo_saldo <= 0:
            novo_status = "PAGO"
            novo_saldo = Decimal("0")
        else:
            hoje = timezone.localdate()
            if self.vencimento and self.vencimento < hoje:
                novo_status = "ATRASO"
            else:
                novo_status = "EM_ABERTO"

        self.total = itens_total
        self.saldo = novo_saldo
        self.status = novo_status
        if commit:
            self.save(update_fields=["total", "saldo", "status"])
        return self.total, self.saldo

class ItemVenda(models.Model):
    conta = models.ForeignKey(ContaCarteira, on_delete=models.CASCADE, related_name="itens")
    produto = models.CharField(max_length=120)
    quantidade = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    valor_unit = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    def subtotal(self):
        return self.quantidade * self.valor_unit

    def __str__(self):
        return f"{self.produto} (x{self.quantidade})"

class Pagamento(models.Model):
    conta = models.ForeignKey(ContaCarteira, on_delete=models.CASCADE, related_name="pagamentos")
    # Data de lançamento/registro (mantida por compatibilidade)
    data = models.DateTimeField(default=timezone.now)
    # NOVO: Data do pagamento efetivo
    data_pagamento = models.DateTimeField(default=timezone.now, db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    observacao = models.CharField(max_length=200, blank=True)

    def __str__(self):
        # Mostra a data efetiva do pagamento
        return f"Pgto {self.valor} em {self.data_pagamento:%d/%m/%Y %H:%M}"

# --- SINAIS: recalcular sempre que itens/pagamentos mudarem ---
@receiver([post_save, post_delete], sender=ItemVenda)
def _recalc_on_change_item(sender, instance, **kwargs):
    instance.conta.atualizar_totais()

@receiver([post_save, post_delete], sender=Pagamento)
def _recalc_on_change_pgto(sender, instance, **kwargs):
    instance.conta.atualizar_totais()

class AuditLog(models.Model):
    ACTION_CHOICES = (
        ("conta_criar", "Criar conta"),
        ("conta_excluir", "Excluir conta"),
        ("conta_restaurar", "Restaurar conta"),
        ("conta_recibo", "Visualizar recibo de conta"),
        ("conta_recibo_print", "Imprimir recibo de conta"),
        ("pgto_registrar", "Registrar pagamento"),
        ("pgto_recibo", "Visualizar recibo de pagamento"),
        ("pgto_recibo_print", "Imprimir recibo de pagamento"),
        ("login", "Login"),
        ("logout", "Logout"),
        ("outro", "Outro"),
    )

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, default="outro")
    descricao = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # metadados úteis
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        who = self.user.username if self.user_id else "anon"
        return f"[{self.created_at:%d/%m/%Y %H:%M}] {who} — {self.action}: {self.descricao[:60]}"
