"""Lightweight, self-contained rate-limiting decorator using Django's cache.

No external packages are needed. On a single PythonAnywhere worker the default
LocMemCache is sufficient; for multiple workers replace CACHES in settings.py
with a shared backend (Redis, Memcached) and the decorator will use it
automatically.
"""

import time
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


RATE_TO_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def _parse_rate(rate):
    """Turn '10/m' into (10, 60)."""
    if not rate:
        return None, None
    parts = rate.split("/")
    count = int(parts[0])
    unit = parts[1].lower() if len(parts) > 1 else "m"
    period = RATE_TO_SECONDS.get(unit, 60)
    return count, period


def _extract_request(args):
    """Return the request object whether the wrapped view is a function or CBV method."""
    for arg in args:
        if hasattr(arg, "META") and hasattr(arg, "user"):
            return arg
    return None


def rate_limit(key="ip", rate="10/m", group=None):
    """Rate-limit a view by IP or authenticated user.

    Usage on a function view:
        @rate_limit(key="ip", rate="5/h", group="register")
        def register_view(request): ...

    Usage on a CBV:
        @method_decorator(rate_limit(key="ip", rate="10/m", group="login"), name="dispatch")
        class LoginView(...): ...
    """
    max_requests, period = _parse_rate(rate)
    if max_requests is None or period is None:
        raise ValueError(f"Invalid rate limit: {rate}")

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(*args, **kwargs):
            request = _extract_request(args)
            if request is None:
                return view_func(*args, **kwargs)

            if key == "user":
                if request.user.is_authenticated:
                    identifier = f"u:{request.user.pk}"
                else:
                    identifier = f"anon:{request.client_ip}"
            else:
                identifier = f"ip:{request.client_ip}"

            bucket = int(time.time() / period)
            cache_key = f"rl:{group or view_func.__name__}:{identifier}:{bucket}"

            # add() is atomic on most Django cache backends (including LocMemCache).
            if not cache.add(cache_key, 1, period):
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, period)

            count = cache.get(cache_key, 1)
            if count > max_requests:
                return HttpResponse(
                    "Too many requests. Please slow down.", status=429
                )

            return view_func(*args, **kwargs)

        return _wrapped

    return decorator
