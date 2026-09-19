"""Fusionne les doublons d'équipes / matchs (migration V4)."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from paris.nettoyage import nettoyer_doublons


class Command(BaseCommand):
    help = (
        'Fusionne les équipes synonymes (alaves / deportivo-alaves, …) '
        'et les matchs en double, et retire les affiches absurdes '
        '(ex. Rome – Le Mans).'
    )

    def handle(self, *args, **options):
        stats = nettoyer_doublons()
        self.stdout.write(self.style.SUCCESS(
            'Nettoyage OK : '
            + ', '.join(f'{k}={v}' for k, v in stats.items())
        ))
