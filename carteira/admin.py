from django.contrib import admin
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento,Empresa, AuditLog


class ItemInline(admin.TabularInline):
    model = ItemVenda
    extra = 0


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0


@admin.register(ContaCarteira)
class ContaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "total", "saldo", "status", "vencimento", "criado_em")
    list_filter = ("status",)
    inlines = [ItemInline, PagamentoInline]


admin.site.register(Cliente)
admin.site.register(Empresa)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "descricao", "ip", "path")
    list_filter = ("action", "created_at")
    search_fields = ("descricao", "user__username", "path", "ip")
    ordering = ("-created_at",)
