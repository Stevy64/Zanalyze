"""Rôles / catégories compte Zanalyze.

Catégories affichées : Visiteur · Membre · Premium
(le champ interne `est_vip` / méthodes `*_vip` restent pour compatibilité).
"""
from __future__ import annotations

CATEGORIES_PREMIUM = frozenset({'premium', 'vip'})  # vip = legacy avant migration
CATEGORIES_VIP = CATEGORIES_PREMIUM  # alias historique


def est_admin(user) -> bool:
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False))
    )


def categorie_user(user) -> str:
    """visiteur | membre | premium (abonnement encore valide)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return 'visiteur'
    # Staff / superuser : Premium permanent (accès admin + app).
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return 'premium'
    from paris.models import Profil
    profil, _ = Profil.objects.get_or_create(user=user)
    if profil.abonnement_vip_actif:
        return 'premium'
    return 'membre'


def est_vip(user) -> bool:
    """True si Premium actif (nom historique conservé)."""
    return categorie_user(user) == 'premium'


def est_premium(user) -> bool:
    return est_vip(user)


def payload_auth(user) -> dict:
    cat = categorie_user(user)
    vip_expire = None
    points = 0
    grade = 'mougou'
    progression = None
    if user and getattr(user, 'is_authenticated', False):
        from paris.models import Profil
        from paris.gamification import grade_pour, progression_utilisateur

        profil = getattr(user, 'profil', None)
        if profil is None:
            profil, _ = Profil.objects.get_or_create(user=user)
        if cat == 'premium' and profil.vip_expire_le:
            vip_expire = profil.vip_expire_le.isoformat()
        points = int(getattr(profil, 'points_premium', 0) or 0)
        grade = grade_pour(points)
        progression = progression_utilisateur(user)
    return {
        'authentifie': bool(user and getattr(user, 'is_authenticated', False)),
        'username': user.username if user and getattr(user, 'is_authenticated', False) else None,
        'categorie': cat,
        'est_vip': cat == 'premium',
        'est_premium': cat == 'premium',
        'est_admin': est_admin(user),
        'vip_expire_le': vip_expire,
        'points_premium': points,
        'grade_premium': grade,
        'progression': progression,
    }
