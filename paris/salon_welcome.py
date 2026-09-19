"""Bienvenue Salon Premium — message collectif + flag d’atterrissage."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def message_bienvenue(username: str, *, renouvellement: bool = False) -> str:
    pseudo = (username or 'ami').strip() or 'ami'
    if renouvellement:
        return (
            f'Encore parmi nous : {pseudo} vient de renouveler son Premium. '
            f'Bienvenue à nouveau dans le Salon — content de te revoir !'
        )
    return (
        f'Nouveau Premium dans le Salon : accueillons {pseudo} ! '
        f'Bienvenue dans la famille Zanalyze — ici on partage tips, vibes et matchs.'
    )


def publier_accueil_salon(profil, *, renouvellement: bool = False) -> None:
    """Poste une annonce système visible par tous + active l’atterrissage Salon."""
    try:
        from paris.models import MessageChat

        user = profil.user
        MessageChat.objects.create(
            auteur=user,
            texte=message_bienvenue(user.username, renouvellement=renouvellement),
            systeme=True,
        )
        if not profil.accueil_salon:
            profil.accueil_salon = True
            profil.save(update_fields=['accueil_salon'])
    except Exception as exc:  # noqa: BLE001
        logger.warning('accueil salon: %s', exc)


def consommer_accueil_salon(user) -> bool:
    """Retourne True si un accueil était en attente, et le consomme."""
    try:
        from paris.models import Profil
        profil = getattr(user, 'profil', None)
        if profil is None:
            profil, _ = Profil.objects.get_or_create(user=user)
        if not profil.accueil_salon:
            return False
        profil.accueil_salon = False
        profil.save(update_fields=['accueil_salon'])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug('consommer accueil: %s', exc)
        return False
