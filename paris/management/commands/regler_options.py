from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from paris.models import Match, Option
from paris.reglement import regler_match


class Command(BaseCommand):
    help = 'Règle les options en attente des matchs terminés.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--apprendre',
            action='store_true',
            help='Option retirée : la calibration est centralisée dans Zanalyze Engine.',
        )

    def handle(self, *args, **opts):
        if opts['apprendre']:
            raise CommandError('Utiliser « python -m engine calibrer » dans Zanalyze Engine. Aucun règlement effectué.')
        qs = (
            Match.objects.filter(statut='termine', buts_dom__isnull=False)
            .select_related('analyse')
            .prefetch_related(
                Prefetch('analyse__options', queryset=Option.objects.filter(resultat='attente')),
            )
        )
        total = 0
        n_matchs = 0
        for match in qs:
            if not hasattr(match, 'analyse'):
                continue
            attente = match.analyse.options.count()
            if attente == 0:
                continue
            n_matchs += 1
            if opts['dry_run']:
                total += attente
                continue
            total += regler_match(match)
        prefix = 'Dry-run : ' if opts['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}{total} options réglées sur {n_matchs} matchs.'
        ))
        if opts['apprendre'] and not opts['dry_run']:
            call_command('apprendre_calibration', stdout=self.stdout)