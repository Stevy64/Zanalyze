"""Middleware analytics (visiteurs / pages) — silencieux en cas d’erreur."""
from __future__ import annotations


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            from paris.analytics import enregistrer_visite
            enregistrer_visite(request)
        except Exception:  # noqa: BLE001
            pass
        return response
