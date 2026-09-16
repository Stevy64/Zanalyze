"""Décroissance quotidienne des points challenge (−1 / 24 h, plancher 0)."""
from django.core.management.base import BaseCommand

from paris.gamification import decroitre_tous_les_profils


class Command(BaseCommand):
    help = 'Applique −1 pt / 24 h sur tous les profils (plancher 0).'

    def handle(self, *args, **options):
        stats = decroitre_tous_les_profils()
        self.stdout.write(self.style.SUCCESS(
            f"Decay OK — {stats['points_retires']} pts retirés "
            f"sur {stats['profils_touches']} profil(s)."
        ))
