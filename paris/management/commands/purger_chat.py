"""Purge des messages du salon de plus de 24 h.

Pour la rétention complète (matchs + comptes), préférer :
  python manage.py purger_retention
"""
from django.core.management.base import BaseCommand

from paris.chat import purger_messages_expires


class Command(BaseCommand):
    help = 'Supprime les messages du salon âgés de plus de 24 heures.'

    def handle(self, *args, **opts):
        n = purger_messages_expires()
        self.stdout.write(self.style.SUCCESS(f'{n} message(s) purgé(s).'))
