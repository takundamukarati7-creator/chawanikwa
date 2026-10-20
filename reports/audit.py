from .models import AuditLog
from .throttle import client_ip


def log_action(request, action: str, target: str = "", detail: str = "") -> None:
    actor = getattr(request, "user", None)
    AuditLog.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action,
        target=target,
        detail=detail[:300],
        ip=client_ip(request) if request is not None else None,
    )
