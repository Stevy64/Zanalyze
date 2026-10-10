import json
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from paris.import_json import ImportInvalide, valider_payload
from paris.models import Match, Option
from paris.sofascore import formater_h2h, statut_depuis_code


EXEMPLE = Path(__file__).resolve().parents[2] / 'exemples' / 'journee-2026-09-08.json'


class ValidationImportTests(TestCase):
    def test_racine_invalide(self):
        with self.assertRaises(ImportInvalide):
            valider_payload([])

    def test_cote_invalide(self):
        data = json.loads(EXEMPLE.read_text(encoding='utf-8'))
        data['matchs'][0]['cotes']['1X2']['1'] = 0.9
        with self.assertRaises(ImportInvalide):
            valider_payload(data)

    def test_exemple_valide(self):
        data = json.loads(EXEMPLE.read_text(encoding='utf-8'))
        self.assertEqual(len(valider_payload(data)), 9)


@override_settings(ZANALYZ_MOTEUR_URL="")
class CommandesTests(TestCase):
    def setUp(self):
        from unittest.mock import patch
        from datetime import datetime, timezone
        clock = patch('django.utils.timezone.now', return_value=datetime(2026, 9, 8, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)

    def test_import_dry_run_n_ecrit_pas(self):
        out = StringIO()
        call_command('importer_matchs', source=str(EXEMPLE), dry_run=True, stdout=out)
        self.assertEqual(Match.objects.count(), 0)
        self.assertIn('Dry-run', out.getvalue())

    def test_import_puis_calcul_idempotent(self):
        call_command('importer_matchs', source=str(EXEMPLE), allow_demo=True, stdout=StringIO())
        n = Match.objects.count()
        self.assertEqual(n, 9)
        call_command('importer_matchs', source=str(EXEMPLE), allow_demo=True, stdout=StringIO())
        self.assertEqual(Match.objects.count(), n)
        call_command('calculer_analyses', journee='2026-09-08', stdout=StringIO())
        m = Match.objects.select_related('analyse').first()
        self.assertTrue(hasattr(m, 'analyse'))
        n_opt = Option.objects.count()
        call_command('calculer_analyses', journee='2026-09-08', stdout=StringIO())
        self.assertEqual(Option.objects.count(), n_opt)

    def test_regler_apres_score(self):
        call_command('importer_matchs', source=str(EXEMPLE), allow_demo=True, stdout=StringIO())
        call_command('calculer_analyses', journee='2026-09-08', stdout=StringIO())
        m = Match.objects.first()
        m.buts_dom, m.buts_ext, m.statut = 2, 1, 'termine'
        m.save()
        out = StringIO()
        call_command('regler_options', stdout=out)
        self.assertIn('options réglées', out.getvalue())
        self.assertTrue(m.analyse.options.exclude(resultat='attente').exists())

    def test_import_fichier_invalide_echoue(self):
        with self.assertRaises(CommandError):
            call_command('importer_matchs', source='nexistepas.json', allow_demo=True)

    def test_import_sans_allow_demo_refuse(self):
        with self.assertRaises(CommandError):
            call_command('importer_matchs', source=str(EXEMPLE), stdout=StringIO())

    def test_recalcul_preserve_options_reglees(self):
        call_command('importer_matchs', source=str(EXEMPLE), allow_demo=True, stdout=StringIO())
        call_command('calculer_analyses', journee='2026-09-08', stdout=StringIO())
        m = Match.objects.filter(statut='a_venir').first()
        # Simule un match encore à venir dont une option a déjà été réglée (edge).
        opt = m.analyse.options.filter(niveau='prudente').first()
        opt.resultat = 'gagne'
        opt.save(update_fields=['resultat'])
        call_command('calculer_analyses', journee='2026-09-08', stdout=StringIO())
        opt.refresh_from_db()
        self.assertEqual(opt.resultat, 'gagne')

    def test_purger_matchs_fictifs(self):
        call_command('importer_matchs', source=str(EXEMPLE), allow_demo=True, stdout=StringIO())
        self.assertEqual(Match.objects.filter(sofascore_id__isnull=True).count(), 9)
        call_command('purger_matchs_fictifs', stdout=StringIO())
        self.assertEqual(Match.objects.count(), 0)


class SofaScoreHelpersTests(TestCase):
    def test_formater_h2h(self):
        texte = formater_h2h(
            {'teamDuel': {'homeWins': 3, 'awayWins': 1, 'draws': 2}},
            'PSG', 'OM',
        )
        self.assertIn('PSG 3', texte)
        self.assertIn('OM 1', texte)
        self.assertEqual(formater_h2h({}, 'A', 'B'), '')

    def test_statut_report(self):
        self.assertEqual(statut_depuis_code(60), 'reporte')
        self.assertEqual(statut_depuis_code(100), 'termine')
        self.assertEqual(statut_depuis_code(6), 'en_cours')


class SnapshotEngineTests(TestCase):
    def test_importer_snapshot_v1(self):
        from pathlib import Path as P
        from tempfile import TemporaryDirectory

        payload = {
            'version': 1,
            'competitions': [{
                'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                'ordre': 20, 'actif': True, 'sofascore_id': 17,
            }],
            'equipes': [
                {'nom': 'Arsenal', 'nom_court': 'Arsenal', 'slug': 'arsenal',
                 'sofascore_id': 42, 'logo_externe': '', 'fiche_club': {}},
                {'nom': 'Chelsea', 'nom_court': 'Chelsea', 'slug': 'chelsea',
                 'sofascore_id': 43, 'logo_externe': '', 'fiche_club': {}},
            ],
            'matchs': [{
                'sofascore_id': 9001,
                'competition_code': 'PL',
                'domicile_slug': 'arsenal',
                'exterieur_slug': 'chelsea',
                'coup_denvoi': '2026-09-20T15:00:00+00:00',
                'journee': '5',
                'statut': 'a_venir',
                'buts_dom': None, 'buts_ext': None,
                'cotes': [{
                    'bookmaker': 'sofascore', 'marche': '1X2', 'selection': '1',
                    'valeur': 1.9, 'nb_sources': 1,
                    'releve_le': '2026-09-19T12:00:00+00:00',
                }],
                'analyse': {
                    'buts_dom_attendus': 1.4, 'buts_ext_attendus': 1.1,
                    'p1': 0.45, 'pn': 0.28, 'p2': 0.27,
                    'score_probable': '1-1', 'profil': 'moyen',
                    'marge_marche': 0.05, 'residu': 0.01,
                    'version_moteur': '3.1.0',
                    'options': [{
                        'famille': '1X2', 'code': '1X2_1', 'libelle': 'Arsenal',
                        'probabilite': 0.45, 'cote_juste': 2.22,
                        'niveau': 'prudente', 'origine': 'marche',
                    }],
                },
            }],
        }
        with TemporaryDirectory() as tmp:
            path = P(tmp) / 'matchs.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            call_command('importer_snapshot', source=str(path), stdout=StringIO())
        self.assertEqual(Match.objects.filter(sofascore_id=9001).count(), 1)
        self.assertTrue(Match.objects.get(sofascore_id=9001).analyse.options.exists())

    def test_importer_snapshot_fichier_absent(self):
        with self.assertRaises(CommandError):
            call_command('importer_snapshot', source='nexistepas-engine.json')

