"""Request-level security middleware: IP/device tags, scanner blocking, logging, CSP."""

import logging
import re

from django.conf import settings
from django.http import HttpResponseForbidden

from apps.accounts.security import get_client_ip, get_device_fingerprint

security_logger = logging.getLogger("security")

# Common low-effort scanner / bot signatures. These are not a full WAF, but
# they stop the most obvious automated probes before they reach Django views.
BLOCKED_USER_AGENTS = re.compile(
    r"sqlmap|nikto|nmap|masscan|zgrab|gobuster|dirb|wfuzz|burp|metasploit|"
    r"python-requests/[0-9]|curl/[0-9]|wget/[0-9]|libwww-perl|java/[0-9]|"
    r"scrapy|ahrefs|semrush|mj12bot|dotbot|petalbot|"
    r"gptbot|chatgpt-user|openai|anthropic|claude-web|"
    r"(bot|crawler|spider)",  # broad catch-all for unknown bots
    re.IGNORECASE,
)

# Paths that are sensitive and should be watched.
SENSITIVE_PATHS = re.compile(r"/(admin|accounts/(login|register|password-reset)|app/humanize)/")


class SecurityContextMiddleware:
    """Attach client_ip and device_fingerprint to every request for views/forms."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = get_client_ip(request)
        request.device_fingerprint = get_device_fingerprint(request)
        response = self.get_response(request)
        return response


class SuspiciousRequestMiddleware:
    """Block obvious scanners and log suspicious traffic to the security logger."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        ip = get_client_ip(request)

        # Block common automated scanners and AI crawlers.
        if BLOCKED_USER_AGENTS.search(user_agent):
            security_logger.warning(
                "Blocked suspicious user-agent: %s from IP %s on %s %s",
                user_agent,
                ip,
                request.method,
                request.path,
            )
            return HttpResponseForbidden("Forbidden.")

        # Log sensitive-path access with no useful UA (often a headless probe).
        if not user_agent and SENSITIVE_PATHS.search(request.path):
            security_logger.warning(
                "Sensitive path %s %s hit with no User-Agent from %s",
                request.method,
                request.path,
                ip,
            )

        response = self.get_response(request)

        # Add a lightweight response header for debugging (not a security header).
        response["X-Content-Type-Options"] = "nosniff"
        return response


class CSPMiddleware:
    """Add a strict Content-Security-Policy header to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy:
            response["Content-Security-Policy"] = policy
        return response
