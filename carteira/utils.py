# carteira/utils.py
from .models import AuditLog

def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # pega o primeiro IP
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

def log_event(request, action, descricao, extra=None):
    try:
        AuditLog.objects.create(
            user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            action=action,
            descricao=descricao,
            path=getattr(request, "path", "")[:255],
            method=getattr(request, "method", "")[:10],
            ip=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:512],
            extra=extra or {},
        )
    except Exception:
        # não quebrar a aplicação por falha de log
        pass
