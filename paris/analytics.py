"""Suivi visiteurs / traces d’activité pour le dashboard admin."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

_SESSION_JOUR = 'zyz_visit_day'
_SKIP_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/sw.js',
    '/manifest',
    '/favicon',
    '/api/v1/sync',
    '/api/v1/health',
)


def _aujourd_hui() -> date:
    return timezone.localdate()


def enregistrer_visite(request) -> None:
    """Compte 1 page vue + 1 visiteur unique / session / jour (hors admin/static)."""
    path = getattr(request, 'path', '') or ''
    if request.method not in ('GET', 'HEAD'):
        return
    if any(path.startswith(p) for p in _SKIP_PREFIXES):
        return
    # Assets / probes
    if path.endswith(('.js', '.css', '.map', '.png', '.jpg', '.webp', '.ico', '.svg', '.woff2')):
        return

    try:
        from paris.models import VisiteJour

        jour = _aujourd_hui()
        row, _ = VisiteJour.objects.get_or_create(jour=jour)
        VisiteJour.objects.filter(pk=row.pk).update(pages_vues=F('pages_vues') + 1)

        session = getattr(request, 'session', None)
        if session is None:
            return
        cle = jour.isoformat()
        if session.get(_SESSION_JOUR) != cle:
            session[_SESSION_JOUR] = cle
            try:
                session.save()
            except Exception:  # noqa: BLE001
                pass
            VisiteJour.objects.filter(pk=row.pk).update(visiteurs=F('visiteurs') + 1)
    except Exception as exc:  # noqa: BLE001 — analytics ne doit jamais casser la requête
        logger.debug('visite: %s', exc)


def enregistrer_trace(
    type_: str,
    label: str,
    *,
    user=None,
    detail: str = '',
    path: str = '',
) -> None:
    try:
        from paris.models import TraceActivite

        TraceActivite.objects.create(
            type=type_ if type_ in dict(TraceActivite.TYPES) else 'autre',
            user=user if getattr(user, 'is_authenticated', False) else None,
            label=(label or '')[:220],
            detail=(detail or '')[:400],
            path=(path or '')[:200],
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug('trace: %s', exc)


def serie_visites(jours: int = 14) -> list[dict]:
    from paris.models import VisiteJour

    fin = _aujourd_hui()
    debut = fin - timedelta(days=jours - 1)
    by_day = {
        v.jour: v
        for v in VisiteJour.objects.filter(jour__gte=debut, jour__lte=fin)
    }
    out = []
    for i in range(jours):
        d = debut + timedelta(days=i)
        v = by_day.get(d)
        out.append({
            'jour': d,
            'label': d.strftime('%d/%m'),
            'visiteurs': v.visiteurs if v else 0,
            'pages_vues': v.pages_vues if v else 0,
        })
    return out


def serie_inscriptions(jours: int = 14) -> list[dict]:
    from django.contrib.auth import get_user_model
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    User = get_user_model()
    fin = _aujourd_hui()
    debut = fin - timedelta(days=jours - 1)
    rows = (
        User.objects.filter(date_joined__date__gte=debut)
        .annotate(j=TruncDate('date_joined'))
        .values('j')
        .annotate(n=Count('id'))
    )
    by_day = {r['j']: r['n'] for r in rows if r['j']}
    out = []
    for i in range(jours):
        d = debut + timedelta(days=i)
        out.append({
            'jour': d,
            'label': d.strftime('%d/%m'),
            'n': by_day.get(d, 0),
        })
    return out
