"""Purge rétention : salon 24 h, matchs > 1 mois, comptes inactifs 6 mois."""
from django.core.management.base import BaseCommand

from paris.retention import purger_retention


class Command(BaseCommand):
    help = (
        'Purge : messages salon (>24 h), matchs terminés (>1 mois), '
        'comptes inactifs (>6 mois).'
    )

    def handle(self, *args, **opts):
        stats = purger_retention()
        self.stdout.write(self.style.SUCCESS(
            f"Purge OK — messages={stats['messages']}, "
            f"matchs={stats['matchs']}, comptes={stats['comptes']}."
        ))
