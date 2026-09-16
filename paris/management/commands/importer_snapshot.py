"""Importe un snapshot JSON (Zanalyze Engine ou export local)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from paris.engine_sync import DEFAULT_ENGINE_URL, snapshot_url
from paris.snapshot import importer_snapshot


class Command(BaseCommand):
    help = (
        'Importe un snapshot v1 (matchs + analyses). '
        'Source : fichier local, --url, ou ZANALYZ_SNAPSHOT_URL '
        '(Zanalyze Engine / GitHub Actions).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            default='exports/matchs.json',
            help='Fichier JSON snapshot local',
        )
        parser.add_argument(
            '--url',
            default='',
            help='URL HTTPS du snapshot (ex. raw.githubusercontent.com)',
        )
        parser.add_argument(
            '--engine',
            action='store_true',
            help='Force l’URL Engine (ZANALYZ_SNAPSHOT_URL ou défaut GitHub).',
        )
        parser.add_argument(
            '--recalculer',
            action='store_true',
            help='Après import, relance calculer_analyses (moteur local).',
        )

    def handle(self, *args, **opts):
        url = (opts.get('url') or '').strip()
        if opts.get('engine') and not url:
            url = snapshot_url()
        if not url:
            url = (os.environ.get('ZANALYZ_SNAPSHOT_URL') or '').strip()

        if url:
            data = self._depuis_url(url)
        else:
            data = self._depuis_fichier(opts['source'])

        stats = importer_snapshot(data)
        self.stdout.write(self.style.SUCCESS(
            'Import snapshot OK : '
            + ', '.join(f'{k}={v}' for k, v in stats.items())
        ))

        if opts['recalculer']:
            from django.core.management import call_command
            self.stdout.write('Recalcul des analyses (moteur local)…')
            call_command('calculer_analyses')

    def _depuis_fichier(self, source: str) -> dict:
        chemin = Path(source)
        if not chemin.is_absolute():
            chemin = Path(settings.BASE_DIR) / chemin
        if not chemin.exists():
            raise CommandError(
                f'Fichier introuvable : {chemin}\n'
                f'Passe --engine ou --url {DEFAULT_ENGINE_URL}'
            )
        try:
            return json.loads(chemin.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'JSON illisible : {exc}') from exc

    def _depuis_url(self, url: str) -> dict:
        from paris.engine_sync import telecharger_snapshot

        self.stdout.write(f'Téléchargement {url} …')
        try:
            data, _digest = telecharger_snapshot(url)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                f'Impossible de télécharger le snapshot ({exc}). '
                f'Essaie : {DEFAULT_ENGINE_URL}'
            ) from exc
        return data
