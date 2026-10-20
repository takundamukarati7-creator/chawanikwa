"""Tiny cache-based rate limiter (per client IP)."""
from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    if settings.TRUST_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def is_limited(request, scope: str) -> bool:
    limit, window = settings.THROTTLES[scope]
    key = f"rl:{scope}:{client_ip(request)}"
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        count = 1
    return count > limit
