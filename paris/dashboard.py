"""Stats activité plateforme pour le dashboard admin."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from paris.analytics import serie_inscriptions, serie_visites
from paris.chat import messages_actifs, seuil_expiration
from paris.models import Match, MessageChat, Option, Profil, TraceActivite
from paris.roles import CATEGORIES_VIP


def _vip_actifs_qs():
    now = timezone.now()
    return Profil.objects.filter(categorie__in=CATEGORIES_VIP).filter(
        Q(vip_expire_le__isnull=True) | Q(vip_expire_le__gt=now),
    )


def build_dashboard_stats() -> dict:
    User = get_user_model()
    now = timezone.now()
    aujourd_hui = timezone.localdate()
    depuis_24h = now - timedelta(hours=24)
    depuis_7j = now - timedelta(days=7)

    n_users = User.objects.filter(is_active=True).count()
    n_vip = _vip_actifs_qs().count()
    n_membres = Profil.objects.filter(categorie='membre').count()
    n_matchs = Match.objects.filter(sofascore_id__isnull=False).count()
    n_a_venir = Match.objects.filter(
        sofascore_id__isnull=False, statut__in=('a_venir', 'en_cours'),
    ).count()
    tips_regles = Option.objects.filter(
        resultat__in=('gagne', 'perdu'),
        niveau__in=('prudente', 'filet'),
    )
    n_tips = tips_regles.count()
    n_gagnes = tips_regles.filter(resultat='gagne').count()
    n_msg_actifs = messages_actifs().count()
    n_msg_24h = MessageChat.objects.filter(created_at__gte=depuis_24h).count()
    n_inscrits_7j = User.objects.filter(date_joined__gte=depuis_7j).count()
    n_inscrits_aujourdhui = User.objects.filter(date_joined__date=aujourd_hui).count()
    n_actifs_7j = User.objects.filter(last_login__gte=depuis_7j).count()

    visites = serie_visites(14)
    inscriptions = serie_inscriptions(14)
    visite_aujourdhui = next((v for v in visites if v['jour'] == aujourd_hui), None)
    n_visiteurs_aujourdhui = visite_aujourdhui['visiteurs'] if visite_aujourdhui else 0
    n_pages_aujourdhui = visite_aujourdhui['pages_vues'] if visite_aujourdhui else 0
    n_visiteurs_7j = sum(v['visiteurs'] for v in visites[-7:])
    max_visiteurs = max((v['visiteurs'] for v in visites), default=1) or 1
    max_inscrits = max((v['n'] for v in inscriptions), default=1) or 1

    for v in visites:
        v['pct'] = round(100 * v['visiteurs'] / max_visiteurs) if max_visiteurs else 0
    for row in inscriptions:
        row['pct'] = round(100 * row['n'] / max_inscrits) if max_inscrits else 0

    derniers_vip = list(
        _vip_actifs_qs()
        .select_related('user')
        .order_by('-vip_depuis', '-id')[:8]
    )
    derniers_msg = list(
        MessageChat.objects.filter(created_at__gte=seuil_expiration())
        .select_related('auteur')
        .order_by('-created_at')[:8]
    )
    traces = list(
        TraceActivite.objects.select_related('user').order_by('-created_at')[:18]
    )
    nouveaux_users = list(
        User.objects.filter(is_active=True).order_by('-date_joined')[:8]
    )

    return {
        'n_users': n_users,
        'n_vip': n_vip,
        'n_membres': n_membres,
        'n_matchs': n_matchs,
        'n_a_venir': n_a_venir,
        'n_tips': n_tips,
        'n_gagnes': n_gagnes,
        'taux_tips': round(100 * n_gagnes / n_tips) if n_tips else None,
        'n_msg_actifs': n_msg_actifs,
        'n_msg_24h': n_msg_24h,
        'n_inscrits_7j': n_inscrits_7j,
        'n_inscrits_aujourdhui': n_inscrits_aujourdhui,
        'n_actifs_7j': n_actifs_7j,
        'n_visiteurs_aujourdhui': n_visiteurs_aujourdhui,
        'n_pages_aujourdhui': n_pages_aujourdhui,
        'n_visiteurs_7j': n_visiteurs_7j,
        'visites': visites,
        'inscriptions': inscriptions,
        'derniers_vip': derniers_vip,
        'derniers_msg': derniers_msg,
        'traces': traces,
        'nouveaux_users': nouveaux_users,
    }
