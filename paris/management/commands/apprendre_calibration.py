"""Ancienne commande conservée pour signaler explicitement la migration."""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'La calibration est désormais apprise exclusivement par Zanalyze Engine.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--depuis', default='')
        parser.add_argument('--jusqu_a', default='')
        parser.add_argument('--min-famille', type=int, default=12)

    def handle(self, *args, **opts):
        raise CommandError(
            'Apprentissage centralisé : exécuter « python -m engine calibrer » '
            'dans Zanalyze Engine, sur ses prédictions figées. '
            'Aucune courbe Django ne sera écrite ni appliquée.'
        )
