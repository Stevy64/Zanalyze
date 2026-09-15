"""Filtrage des bilans matchs passés selon le rôle."""
from __future__ import annotations

from paris.roles import est_admin, est_premium

# Tips visibles hors Premium/admin sur un match terminé (sans justifications).
NIVEAUX_BILAN_PUBLIC = frozenset({'prudente', 'filet'})


def peut_bilan_complet(user) -> bool:
    """Bilan complet (tous tips + détails) : admin ou Premium."""
    return est_admin(user) or est_premium(user)


def filtrer_options_bilan(user, match, options: list) -> list:
    """Sur match terminé : admin/Premium = tout ; sinon prudente + filet."""
    if getattr(match, 'statut', None) != 'termine':
        return list(options)
    if peut_bilan_complet(user):
        return list(options)
    return [o for o in options if getattr(o, 'niveau', None) in NIVEAUX_BILAN_PUBLIC]


def peut_details_option(user, match) -> bool:
    """Justifications / méta : Premium (et admin) sur tous les matchs."""
    return est_premium(user) or est_admin(user)
