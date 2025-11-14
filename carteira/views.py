from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Sum, Case, When, DecimalField, F, Q, ExpressionWrapper
from django.contrib.auth.decorators import login_required
from .models import Cliente, ContaCarteira, ItemVenda, Pagamento, Empresa, AuditLog
from django.utils import timezone
from .forms import (
    ClienteForm, ContaForm, ItemInlineForm, PagamentoForm,
    DeleteConfirmForm, RestoreConfirmForm
)
from django.forms import formset_factory
from datetime import timedelta
from decimal import Decimal
import random
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth import get_user_model
from .utils import log_event


# ====== CONSTANTS / HELPERS ======
User = get_user_model()
DEC = DecimalField(max_digits=12, decimal_places=2)
ALLOWED_SORTS = {"id": "id", "nome": "cliente__nome", "vencimento": "vencimento"}

ItemFormSet = formset_factory(ItemInlineForm, extra=1, can_delete=True)


def _apply_filters(qs, params):
    q = params.get("q", "").strip()
    status = params.get("status", "").strip()
    venc_ini = params.get("venc_ini", "").strip()
    venc_fim = params.get("venc_fim", "").strip()

    if q:
        qs = qs.filter(Q(cliente__nome__icontains=q) | Q(id__icontains=q))
    if status in {"EM_ABERTO", "PAGO", "ATRASO"}:
        qs = qs.filter(status=status)
    if venc_ini:
        qs = qs.filter(vencimento__gte=venc_ini)
    if venc_fim:
        qs = qs.filter(vencimento__lte=venc_fim)
    return qs


def _order_qs(qs, sort_key, direction):
    field = ALLOWED_SORTS.get(sort_key, "id")
    prefix = "" if direction == "asc" else "-"
    # secondary key keeps id deterministic
    return qs.order_by(f"{prefix}{field}", f"{'-' if direction=='desc' else ''}id")


# ====== VIEWS ======
@login_required
def dashboard(request):
    sort_key = request.GET.get("sort", "id").lower()
    direction = request.GET.get("dir", "desc").lower()

    base_qs = ContaCarteira.objects.filter(owner=request.user, is_deleted=False)
    qs = _apply_filters(base_qs, request.GET)

    # pago = total - saldo (independe de status)
    pago_expr = ExpressionWrapper(F("total") - F("saldo"), output_field=DEC)

    agg = qs.aggregate(
        total_face=Sum("total", default=Decimal("0.00")),
        total_saldo=Sum("saldo", default=Decimal("0.00")),
        total_pago=Sum(pago_expr, default=Decimal("0.00")),
        total_em_aberto=Sum(
            Case(When(status="EM_ABERTO", then=F("saldo")),
                 default=Decimal("0.00"), output_field=DEC),
            default=Decimal("0.00"),
        ),
        total_em_atraso=Sum(
            Case(When(status="ATRASO", then=F("saldo")),
                 default=Decimal("0.00"), output_field=DEC),
            default=Decimal("0.00"),
        ),
    )
    a_receber = (agg["total_em_aberto"] or Decimal("0")) + (agg["total_em_atraso"] or Decimal("0"))

    qs_annot = qs.annotate(pago=pago_expr)
    atrasados = _order_qs(qs_annot.filter(status="ATRASO"), sort_key, direction).select_related("cliente")
    em_aberto = _order_qs(qs_annot.filter(status="EM_ABERTO"), sort_key, direction).select_related("cliente")
    quitados = _order_qs(qs_annot.filter(status="PAGO"), sort_key, direction).select_related("cliente")

    base_params_qd = request.GET.copy()
    base_params_qd.pop("sort", None)
    base_params_qd.pop("dir", None)
    base_params = base_params_qd.urlencode()

    def _icon(col):
        return "▲" if request.GET.get("sort")==col and request.GET.get("dir")=="asc" else ("▼" if request.GET.get("sort")==col else "")

    def _next(col):
        cur = request.GET.get("sort")
        d = request.GET.get("dir", "desc")
        return "asc" if cur==col and d=="desc" else "desc"

    context = {
        "q": request.GET.get("q", ""),
        "atrasados": atrasados,
        "em_aberto": em_aberto,
        "quitados": quitados,
        "totais": {
            "pago": agg["total_pago"] or Decimal("0"),
            "a_receber": a_receber,
            "em_aberto": agg["total_em_aberto"] or Decimal("0"),
            "em_atraso": agg["total_em_atraso"] or Decimal("0"),
            "face_value_total": agg["total_face"] or Decimal("0"),
            "saldo_total": agg["total_saldo"] or Decimal("0"),
        },
        "base_params": base_params,
        "sort": {
            "current": request.GET.get("sort","id"),
            "dir": request.GET.get("dir","desc"),
            "icon": {"id": _icon("id"), "nome": _icon("nome"), "vencimento": _icon("vencimento")},
            "next": {"id": _next("id"), "nome": _next("nome"), "vencimento": _next("vencimento")},
        },
        # IMPORTANTE para o modal Nova Conta
        "cliente_form": ClienteForm(),
        "conta_form": ContaForm(),
        "item_formset": ItemFormSet(prefix="itens"),
        # IMPORTANTE para o modal Excluir Conta (evita erro de campos vazios)
        "del_form": DeleteConfirmForm(),
    }
    return render(request, "carteira/dashboard.html", context)


@login_required
@require_GET
def api_clientes_busca(request):
    """
    Retorna até 10 clientes do usuário logado cujo nome contenha o termo informado.
    Usado no autocomplete do modal de Nova Conta.
    """
    termo = request.GET.get("q", "").strip()
    if len(termo) < 2:
        return JsonResponse({"results": []})

    qs = (
        Cliente.objects
        .filter(owner=request.user, nome__icontains=termo)
        .order_by("nome")[:10]
    )

    data = []
    for c in qs:
        data.append({
            "id": c.id,
            "nome": c.nome,
            "cpf": c.cpf or "",
            "telefone": c.telefone or "",
            "email": c.email or "",
            "endereco": c.endereco or "",
        })
    return JsonResponse({"results": data})


def _get_conta_or_404(user, conta_id, include_deleted=False):
    qs = ContaCarteira.objects.filter(owner=user).select_related("cliente")
    if not include_deleted:
        qs = qs.filter(is_deleted=False)
    return get_object_or_404(qs, pk=conta_id)


@login_required
def clientes_lista(request):
    user = request.user

    qs = Cliente.objects.filter(owner=user)  # só clientes do usuário logado

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(nome__icontains=q) |
            Q(cpf__icontains=q) |
            Q(telefone__icontains=q) |
            Q(email__icontains=q)
        )

    qs = qs.order_by("nome")

    context = {
        "clientes": qs,
        "q": q,
        "total_clientes": qs.count(),
    }
    return render(request, "carteira/clientes_lista.html", context)


@login_required
@transaction.atomic
def nova_conta(request):
    if request.method != "POST":
        return redirect("carteira:dashboard")

    cliente_id = request.POST.get("cliente_id", "").strip() or None

    conta_form = ContaForm(request.POST)
    formset = ItemFormSet(request.POST, prefix="itens")

    cliente = None
    cform = None

    # ====== CASO 1: CLIENTE EXISTENTE ======
    if cliente_id:
        if conta_form.is_valid() and formset.is_valid():
            cliente = get_object_or_404(Cliente, pk=cliente_id, owner=request.user)

            conta = ContaCarteira.objects.create(
                owner=request.user,
                cliente=cliente,
                vencimento=conta_form.cleaned_data.get("vencimento"),
            )

            for form in formset:
                cd = form.cleaned_data
                if not cd or cd.get("DELETE"):
                    continue
                ItemVenda.objects.create(
                    conta=conta,
                    produto=cd["produto"],
                    quantidade=cd["quantidade"],
                    valor_unit=cd["valor_unit"],
                )

            conta.atualizar_totais()
            messages.success(request, f"Conta #{conta.id} criada para {cliente.nome}.")
            log_event(
                request,
                action="conta_criar",
                descricao=f"Usuário {request.user}: Criou conta #{conta.id} para {cliente.nome}",
                extra={"conta_id": conta.id, "cliente_id": cliente.id},
            )
            return redirect("carteira:recibo_conta", conta_id=conta.id)
        else:
            messages.error(request, "Corrija os erros no formulário.")
    # ====== CASO 2: NOVO CLIENTE ======
    else:
        cform = ClienteForm(request.POST)
        if cform.is_valid() and conta_form.is_valid() and formset.is_valid():
            # 👇 AQUI ESTAVA O PROBLEMA
            cliente = cform.save(commit=False)
            cliente.owner = request.user        # define o dono
            cliente.save()

            conta = ContaCarteira.objects.create(
                owner=request.user,
                cliente=cliente,
                vencimento=conta_form.cleaned_data.get("vencimento"),
            )

            for form in formset:
                cd = form.cleaned_data
                if not cd or cd.get("DELETE"):
                    continue
                ItemVenda.objects.create(
                    conta=conta,
                    produto=cd["produto"],
                    quantidade=cd["quantidade"],
                    valor_unit=cd["valor_unit"],
                )

            conta.atualizar_totais()
            messages.success(request, f"Conta #{conta.id} criada para {cliente.nome}.")
            log_event(
                request,
                action="conta_criar",
                descricao=f"Usuário {request.user}: Criou conta #{conta.id} para {cliente.nome}",
                extra={"conta_id": conta.id, "cliente_id": cliente.id},
            )
            return redirect("carteira:recibo_conta", conta_id=conta.id)
        else:
            messages.error(request, "Corrija os dados do cliente e da conta.")

    # ====== Se chegou aqui, teve erro → re-renderiza dashboard com modal aberto ======
    base = ContaCarteira.objects.filter(owner=request.user, is_deleted=False).select_related("cliente")
    atrasados = base.filter(status="ATRASO")
    em_aberto = base.filter(status="EM_ABERTO")
    quitados = base.filter(status="PAGO")

    return render(request, "carteira/dashboard.html", {
        "q": request.GET.get("q", "").strip(),
        "atrasados": atrasados.order_by("vencimento", "id"),
        "em_aberto": em_aberto.order_by("vencimento", "id"),
        "quitados": quitados.order_by("vencimento", "id"),
        "cliente_form": cform or ClienteForm(),
        "conta_form": conta_form,
        "item_formset": formset,
        "del_form": DeleteConfirmForm(),
        "open_modal": True,
    })


@login_required
def conta_detalhe(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id)
    pgform = PagamentoForm()
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
            # Se a data não foi informada, usa agora:
            if not pgto.data_pagamento:
                pgto.data_pagamento = timezone.now()
            pgto.save()

            log_event(
                request,
                action="pgto_registrar",
                descricao=f"Usuário {request.user}: Registrou pagamento #{pgto.id} na conta #{conta.id} (R$ {pgto.valor})",
                extra={"conta_id": conta.id, "pagamento_id": pgto.id, "valor": str(pgto.valor)}
            )
            messages.success(request, "Pagamento registrado com sucesso.")
            return redirect("carteira:recibo_pagamento", pagamento_id=pgto.id)
        else:
            messages.error(request, "Não foi possível registrar: verifique o valor e a data do pagamento.")
            return redirect("carteira:conta", conta_id=conta.id)
    return redirect("carteira:conta", conta_id=conta.id)


@login_required
def recibo_conta(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id)
    empresa = getattr(request.user, "empresa", None)
    from .utils import log_event
    log_event(request, action="conta_recibo", descricao=f"Usuário {request.user}: Acessou recibo da conta #{conta.id}", extra={"conta_id": conta.id})
    if request.GET.get("print"):
        log_event(request, action="conta_recibo_print", descricao=f"Usuário {request.user}: Imprimiu recibo da conta #{conta.id}", extra={"conta_id": conta.id})
    return render(request, "carteira/recibo_conta.html", {"conta": conta, "empresa": empresa})

@login_required
def recibo_pagamento(request, pagamento_id):
    pg = get_object_or_404(Pagamento.objects.select_related("conta", "conta__cliente"), pk=pagamento_id)
    empresa = getattr(request.user, "empresa", None)
    if pg.conta.owner_id != request.user.id:
        return redirect("carteira:dashboard")
    from .utils import log_event
    log_event(request, action="pgto_recibo", descricao=f"Usuário {request.user}: Acessou recibo do pagamento #{pg.id} (conta #{pg.conta_id})", extra={"pagamento_id": pg.id, "conta_id": pg.conta_id})
    if request.GET.get("print"):
        log_event(request, action="pgto_recibo_print", descricao=f"Usuário {request.user}: Imprimiu recibo do pagamento #{pg.id} (conta #{pg.conta_id})", extra={"pagamento_id": pg.id, "conta_id": pg.conta_id})
    return render(request, "carteira/recibo_pagamento.html", {"pg": pg, "empresa": empresa})

@require_POST
@login_required
@transaction.atomic
def excluir_conta(request, conta_id):
    """Marca uma ContaCarteira como excluída (soft delete) após validar a senha e receber o motivo."""
    conta = _get_conta_or_404(request.user, conta_id, include_deleted=False)
    form = DeleteConfirmForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o motivo e a sua senha.")
        return redirect(request.META.get("HTTP_REFERER") or "carteira:conta", conta_id=conta.id)

    motivo = form.cleaned_data["motivo"].strip()
    senha = form.cleaned_data["senha"]

    if not request.user.check_password(senha):
        messages.error(request, "Senha incorreta. Exclusão não realizada.")
        return redirect(request.META.get("HTTP_REFERER") or "carteira:conta", conta_id=conta.id)

    conta.is_deleted = True
    conta.deleted_at = timezone.now()
    conta.deleted_reason = motivo
    conta.deleted_by = request.user
    conta.save(update_fields=["is_deleted", "deleted_at", "deleted_reason", "deleted_by"])

    from .utils import log_event
    log_event(request, action="conta_excluir", descricao=f"Usuário {request.user}: Excluiu conta #{conta.id} de {conta.cliente.nome} (motivo: {motivo})", extra={"conta_id": conta.id, "motivo": motivo})

    cliente_nome = getattr(conta.cliente, "nome", str(conta.cliente_id))
    messages.success(request, f"Conta #{conta_id} de {cliente_nome} marcada como excluída.")
    return redirect("carteira:dashboard")

@login_required
def excluidos(request):
    q = request.GET.get("q", "").strip()
    base = ContaCarteira.objects.filter(owner=request.user, is_deleted=True).select_related("cliente")
    if q:
        base = base.filter(cliente__nome__icontains=q)
    contas = base.order_by("-deleted_at", "-id")
    return render(request, "carteira/excluidos.html", {"q": q, "contas": contas})

@login_required
@transaction.atomic
def restaurar_conta(request, conta_id):
    conta = _get_conta_or_404(request.user, conta_id, include_deleted=True)
    if not conta.is_deleted:
        messages.info(request, f"A conta #{conta.id} não está excluída.")
        from .utils import log_event
        log_event(request, action="conta_restaurar", descricao=f"Usuário {request.user}: Erro, a conta #{conta.id} de {conta.cliente.nome} náo estava excluida.", extra={"conta_id": conta.id})
        return redirect("carteira:dashboard")

    if request.method == "POST":
        form = RestoreConfirmForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe sua senha para confirmar.")
            return redirect("carteira:excluidos")

        senha = form.cleaned_data["senha"]
        if not request.user.check_password(senha):
            messages.error(request, "Senha incorreta. A restauração não foi realizada.")
            return redirect("carteira:excluidos")

        conta.is_deleted = False
        conta.deleted_at = None
        conta.deleted_reason = ""
        conta.deleted_by = None
        conta.save(update_fields=["is_deleted", "deleted_at", "deleted_reason", "deleted_by"])

        from .utils import log_event
        log_event(request, action="conta_restaurar", descricao=f"Usuário {request.user}: Restaurou conta #{conta.id} de {conta.cliente.nome}", extra={"conta_id": conta.id})

        messages.success(request, f"Conta #{conta.id} de {conta.cliente.nome} foi restaurada com sucesso.")
        return redirect("carteira:excluidos")

    return redirect("carteira:excluidos")

@login_required
def historico(request):
    q = request.GET.get("q", "").strip()
    base = AuditLog.objects.filter(user=request.user)
    if q:
        base = base.filter(descricao__icontains=q)
    logs = base.order_by("-created_at", "-id")[:500]
    return render(request, "carteira/historico.html", {"logs": logs, "q": q})

# ====== SEED (apenas staff) ======
@staff_member_required
@require_GET
def seed_contas_fixas(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "auth required"}, status=401)

    n_pago = int(request.GET.get("pago", 5))
    n_atraso = int(request.GET.get("atraso", 10))
    n_aberto = int(request.GET.get("aberto", 15))

    hoje = timezone.localdate()

    def _rand_money(min_cent=1000, max_cent=200000):
        return Decimal(random.randint(min_cent, max_cent)) / Decimal(100)

    def _ensure_clientes(qtd, prefixo):
        clientes = []
        for i in range(qtd):
            nome = f"{prefixo} {i+1:02d}"
            c, _ = Cliente.objects.get_or_create(nome=nome)
            clientes.append(c)
            # Caso seu Cliente exija campos extras, ajuste aqui.
        return clientes

    clientes_pago = _ensure_clientes(max(n_pago, 1), "Cliente Seed Pago")
    clientes_atraso = _ensure_clientes(max(n_atraso, 1), "Cliente Seed Atraso")
    clientes_aberto = _ensure_clientes(max(n_aberto, 1), "Cliente Seed Aberto")

    criadas = {"PAGO": [], "ATRASO": [], "EM_ABERTO": []}

    # PAGO
    objs = []
    for i in range(n_pago):
        total = _rand_money()
        criado_em = hoje - timedelta(days=random.randint(1, 120))
        venc = hoje - timedelta(days=random.randint(1, 90))
        objs.append(ContaCarteira(
            owner=request.user, cliente=clientes_pago[i % len(clientes_pago)],
            criado_em=criado_em, vencimento=venc, total=total, saldo=Decimal("0.00"), status="PAGO",
        ))
    created = ContaCarteira.objects.bulk_create(objs, batch_size=200)
    criadas["PAGO"] = [c.id for c in created]

    # ATRASO
    objs = []
    for i in range(n_atraso):
        total = _rand_money()
        criado_em = hoje - timedelta(days=random.randint(1, 120))
        venc = hoje - timedelta(days=random.randint(1, 60))
        objs.append(ContaCarteira(
            owner=request.user, cliente=clientes_atraso[i % len(clientes_atraso)],
            criado_em=criado_em, vencimento=venc, total=total, saldo=total, status="ATRASO",
        ))
    created = ContaCarteira.objects.bulk_create(objs, batch_size=200)
    criadas["ATRASO"] = [c.id for c in created]

    # EM_ABERTO
    objs = []
    for i in range(n_aberto):
        total = _rand_money()
        criado_em = hoje - timedelta(days=random.randint(0, 30))
        venc = hoje + timedelta(days=random.randint(1, 180))
        objs.append(ContaCarteira(
            owner=request.user, cliente=clientes_aberto[i % len(clientes_aberto)],
            criado_em=criado_em, vencimento=venc, total=total, saldo=total, status="EM_ABERTO",
        ))
    created = ContaCarteira.objects.bulk_create(objs, batch_size=200)
    criadas["EM_ABERTO"] = [c.id for c in created]

    return redirect("carteira:dashboard")