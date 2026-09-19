"""Rétention données : salon 24 h, matchs > 1 mois, comptes inactifs 6 mois."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from paris.chat import purger_messages_expires
from paris.models import Match

User = get_user_model()

RETENTION_MATCHS = timedelta(days=30)
RETENTION_COMPTES_INACTIFS = timedelta(days=183)  # ~6 mois


def purger_matchs_anciens(*, jours: int = 30) -> int:
    """Supprime les matchs terminés / reportés plus vieux que N jours."""
    seuil = timezone.now() - timedelta(days=max(1, int(jours)))
    qs = Match.objects.filter(
        statut__in=('termine', 'reporte'),
        coup_denvoi__lt=seuil,
    )
    n, _ = qs.delete()
    return int(n)


def purger_comptes_inactifs(*, jours: int = 183) -> int:
    """
    Supprime les comptes non-staff inactifs depuis N jours.
    Critère : last_login (sinon date_joined) antérieur au seuil.
    """
    seuil = timezone.now() - timedelta(days=max(30, int(jours)))
    qs = (
        User.objects
        .filter(is_staff=False, is_superuser=False)
        .filter(
            Q(last_login__lt=seuil)
            | Q(last_login__isnull=True, date_joined__lt=seuil)
        )
    )
    n, _ = qs.delete()
    return int(n)


def purger_retention() -> dict[str, int]:
    """Enchaîne les purges métier (salon, matchs, comptes)."""
    return {
        'messages': purger_messages_expires(),
        'matchs': purger_matchs_anciens(),
        'comptes': purger_comptes_inactifs(),
    }
