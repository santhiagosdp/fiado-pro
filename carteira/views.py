
from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required  # NEW
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento, Empresa, AuditLog
from django.utils import timezone
from django.contrib.auth import authenticate  # opcional
from .forms import ClienteForm, ContaForm, ItemFormSet, PagamentoForm, DeleteConfirmForm  # + DeleteConfirmForm
from .utils import log_event


@login_required
def dashboard(request):
    q = request.GET.get("q", "").strip()

    base = (ContaCarteira.objects
            .filter(owner=request.user, is_deleted=False)  # garante esconder excluídos
            .select_related("cliente"))
    base_atrasados = base.filter(status="ATRASO")
    base_em_aberto = base.filter(status="EM_ABERTO")
    base_quitados  = base.filter(status="PAGO")

    if q:
        name_filter = Q(cliente__nome__icontains=q)
        atrasados = base_atrasados.filter(name_filter)
        em_aberto = base_em_aberto.filter(name_filter)
        quitados  = base_quitados.filter(name_filter)
    else:
        atrasados = base_atrasados
        em_aberto = base_em_aberto
        quitados  = base_quitados

    cform = ClienteForm()
    conta_form = ContaForm()
    formset = ItemFormSet(prefix="itens")
    del_form = DeleteConfirmForm()  # + NEW

    return render(request, "carteira/dashboard.html", {
        "q": q,
        "atrasados": atrasados.order_by("vencimento", "id"),
        "quitados": quitados.order_by("vencimento", "id"),
        "em_aberto": em_aberto.order_by("vencimento", "id"),
        "cform": cform,
        "conta_form": conta_form,
        "formset": formset,
        "del_form": del_form,        # + NEW
        "open_modal": False,
    })

 
def _get_conta_or_404(user, conta_id, include_deleted=False):
    qs = ContaCarteira.objects.filter(owner=user).select_related("cliente")
    if not include_deleted:
        qs = qs.filter(is_deleted=False)
    return get_object_or_404(qs, pk=conta_id)


@login_required
@transaction.atomic
def nova_conta(request):
    if request.method != "POST":
        return redirect("carteira:dashboard")

    cform = ClienteForm(request.POST)
    conta_form = ContaForm(request.POST)
    formset = ItemFormSet(request.POST, prefix="itens")

    if cform.is_valid() and conta_form.is_valid() and formset.is_valid():
        # 1) Cliente
        cliente = cform.save()

        # 2) Conta (bind to user)
        conta = ContaCarteira.objects.create(
            owner=request.user,  # NEW
            cliente=cliente,
            vencimento=conta_form.cleaned_data.get("vencimento"),
        )

        # 3) Itens
        for form in formset:
            cd = form.cleaned_data
            if not cd:
                continue
            if cd.get("DELETE"):
                continue
            ItemVenda.objects.create(
                conta=conta,
                produto=cd["produto"],
                quantidade=cd["quantidade"],
                valor_unit=cd["valor_unit"],
            )

        # 4) Totais
        conta.atualizar_totais()

        messages.success(request, f"Conta #{conta.id} criada para {cliente.nome}.")
        log_event(request,
          action="conta_criar",
          descricao=f"Usuário {request.user}: Criou conta #{conta.id} para {cliente.nome}",
          extra={"conta_id": conta.id, "cliente_id": cliente.id})
        return redirect("carteira:recibo_conta", conta_id=conta.id)

    # If invalid, re-render with modal open
    base = ContaCarteira.objects.filter(owner=request.user).select_related("cliente")
    atrasados = base.filter(status="ATRASO")
    em_aberto = base.filter(status="EM_ABERTO")
    quitados  = base.filter(status="PAGO")

    messages.error(request, "Corrija os erros no formulário.")
    return render(request, "carteira/dashboard.html", {
        "q": request.GET.get("q", "").strip(),
        "atrasados": atrasados.order_by("vencimento", "id"),
        "em_aberto": em_aberto.order_by("vencimento", "id"),
        "quitados": quitados.order_by("vencimento", "id"),
        "cform": cform,
        "conta_form": conta_form,
        "formset": formset,
        "open_modal": True,
    })


@login_required
def conta_detalhe(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id)
    pgform = PagamentoForm()
    # disponibiliza também o form de excluir (para modal no template, se quiser)
    del_form = DeleteConfirmForm()
    return render(request, "carteira/conta_detalhe.html", {"conta": conta, "pgform": pgform, "del_form": del_form})


@login_required
@transaction.atomic
def pagar(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id)
    if request.method == "POST":
        form = PagamentoForm(request.POST)
        if form.is_valid():
            pgto = form.save(commit=False)
            pgto.conta = conta
            pgto.save()
            log_event(request,
                action="pgto_registrar",
                descricao=f"Usuário {request.user}: Registrou pagamento #{pgto.id} na conta #{conta.id} (R$ {pgto.valor})",
                extra={"conta_id": conta.id, "pagamento_id": pgto.id, "valor": str(pgto.valor)}
            )

            messages.success(request, "Pagamento registrado com sucesso.")
            return redirect("carteira:recibo_pagamento", pagamento_id=pgto.id)
    return redirect("carteira:conta", conta_id=conta.id)


@login_required
def recibo_conta(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id)
    empresa = request.user.empresa

    # log: visualização
    log_event(request,
              action="conta_recibo",
              descricao=f"Usuário {request.user}: Acessou recibo da conta #{conta.id}",
              extra={"conta_id": conta.id})

    # se vier ?print=1, considerar como 'impressão'
    if request.GET.get("print"):
        log_event(request,
                  action="conta_recibo_print",
                  descricao=f"Usuário {request.user}: Imprimiu recibo da conta #{conta.id}",
                  extra={"conta_id": conta.id})
    return render(request, "carteira/recibo_conta.html", {"conta": conta, "empresa" : empresa})


@login_required
def recibo_pagamento(request, pagamento_id):
    pg = get_object_or_404(Pagamento.objects.select_related("conta", "conta__cliente"), pk=pagamento_id)
    empresa = request.user.empresa

    if pg.conta.owner_id != request.user.id:
        return redirect("carteira:dashboard")

    log_event(request,
              action="pgto_recibo",
              descricao=f"Usuário {request.user}: Acessou recibo do pagamento #{pg.id} (conta #{pg.conta_id})",
              extra={"pagamento_id": pg.id, "conta_id": pg.conta_id})

    if request.GET.get("print"):
        log_event(request,
                  action="pgto_recibo_print",
                  descricao=f"Usuário {request.user}: Imprimiu recibo do pagamento #{pg.id} (conta #{pg.conta_id})",
                  extra={"pagamento_id": pg.id, "conta_id": pg.conta_id})

    return render(request, "carteira/recibo_pagamento.html", {"pg": pg, "empresa" : empresa })


@require_POST
@login_required
@transaction.atomic
def excluir_conta(request, conta_id):
    """
    Marca uma ContaCarteira como excluída (soft delete) após validar a senha e receber o motivo.
    """
    conta = _get_conta_or_404(request.user, conta_id, include_deleted=False)

    form = DeleteConfirmForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o motivo e a sua senha.")
        return redirect(request.META.get("HTTP_REFERER") or "carteira:conta", conta_id=conta.id)

    motivo = form.cleaned_data["motivo"].strip()
    senha = form.cleaned_data["senha"]

    # Valida a senha do usuário logado sem trocar backend:
    if not request.user.check_password(senha):
        messages.error(request, "Senha incorreta. Exclusão não realizada.")
        return redirect(request.META.get("HTTP_REFERER") or "carteira:conta", conta_id=conta.id)

    # Soft delete:
    conta.is_deleted = True
    conta.deleted_at = timezone.now()
    conta.deleted_reason = motivo
    conta.deleted_by = request.user
    conta.save(update_fields=["is_deleted", "deleted_at", "deleted_reason", "deleted_by"])

    log_event(request,
            action="conta_excluir",
            descricao=f"Usuário {request.user}: Excluiu conta #{conta.id} de {conta.cliente.nome} (motivo: {motivo})",
            extra={"conta_id": conta.id, "motivo": motivo})

    cliente_nome = getattr(conta.cliente, "nome", str(conta.cliente_id))
    messages.success(request, f"Conta #{conta_id} de {cliente_nome} marcada como excluída.")
    return redirect("carteira:excluidos")


@login_required
def excluidos(request):
    """Lista somente as contas marcadas como excluídas do usuário logado."""
    q = request.GET.get("q", "").strip()
    base = (ContaCarteira.objects
            .filter(owner=request.user, is_deleted=True)
            .select_related("cliente"))
    if q:
        base = base.filter(cliente__nome__icontains=q)

    contas = base.order_by("-deleted_at", "-id")
    return render(request, "carteira/excluidos.html", {
        "q": q,
        "contas": contas,
    })


@login_required
@transaction.atomic
def restaurar_conta(request, conta_id):
    """Cancela a exclusão (restaura uma conta marcada como excluída)."""
    conta = _get_conta_or_404(request.user, conta_id, include_deleted=True)

    if not conta.is_deleted:
        messages.info(request, f"A conta #{conta.id} não está excluída.")
        log_event(request,
          action="conta_restaurar",
          descricao=f"Usuário {request.user}: Erro, a conta #{conta.id} de {conta.cliente.nome} náo estava excluida.",
          extra={"conta_id": conta.id})
        return redirect("carteira:dashboard")

    if request.method == "POST":
        from .forms import RestoreConfirmForm
        form = RestoreConfirmForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Informe sua senha para confirmar.")
            return redirect("carteira:excluidos")

        senha = form.cleaned_data["senha"]

        # Verifica a senha do usuário logado
        if not request.user.check_password(senha):
            messages.error(request, "Senha incorreta. A restauração não foi realizada.")
            return redirect("carteira:excluidos")

        # Restaurar conta
        conta.is_deleted = False
        conta.deleted_at = None
        conta.deleted_reason = ""
        conta.deleted_by = None
        conta.save(update_fields=["is_deleted", "deleted_at", "deleted_reason", "deleted_by"])

        log_event(request,
          action="conta_restaurar",
          descricao=f"Usuário {request.user}: Restaurou conta #{conta.id} de {conta.cliente.nome}",
          extra={"conta_id": conta.id})

        messages.success(request, f"Conta #{conta.id} de {conta.cliente.nome} foi restaurada com sucesso.")
        return redirect("carteira:excluidos")

    # GET — redireciona caso tentem acessar sem POST
    return redirect("carteira:excluidos")


@login_required
def historico(request):
    q = request.GET.get("q", "").strip()
    base = AuditLog.objects.filter(user=request.user)
    if q:
        base = base.filter(descricao__icontains=q)
    logs = base.order_by("-created_at", "-id")[:500]
    return render(request, "carteira/historico.html", {"logs": logs, "q": q})
