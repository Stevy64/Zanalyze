"""Tests snapshot export / import."""

from datetime import datetime, timezone as dt_timezone

from django.test import TestCase
from django.utils import timezone

from paris.models import Analyse, Competition, Cote, Equipe, Match, Option
from paris.snapshot import exporter_snapshot, importer_snapshot


class SnapshotRoundtripTests(TestCase):
    def setUp(self):
        self.comp = Competition.objects.create(
            code='PL', nom='Premier League', ordre=20, sofascore_id=17,
        )
        self.dom = Equipe.objects.create(
            nom='Home FC', nom_court='Home', slug='home-fc', sofascore_id=1,
        )
        self.ext = Equipe.objects.create(
            nom='Away FC', nom_court='Away', slug='away-fc', sofascore_id=2,
        )
        self.match = Match.objects.create(
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=timezone.now(),
            statut='a_venir',
            sofascore_id=424242,
        )
        Cote.objects.create(
            match=self.match, bookmaker='snapshot', marche='1X2',
            selection='1', valeur='1.90', releve_le=timezone.now(),
        )
        Cote.objects.create(
            match=self.match, bookmaker='snapshot', marche='1X2',
            selection='N', valeur='3.40', releve_le=timezone.now(),
        )
        Cote.objects.create(
            match=self.match, bookmaker='snapshot', marche='1X2',
            selection='2', valeur='4.00', releve_le=timezone.now(),
        )
        ana = Analyse.objects.create(
            match=self.match,
            buts_dom_attendus=1.5, buts_ext_attendus=1.1,
            p1=0.45, pn=0.28, p2=0.27,
            score_probable='1-1', profil='moyen',
            marge_marche=0.05, residu=0.01, version_moteur='3.1.0',
        )
        Option.objects.create(
            analyse=ana, famille='Total buts', code='UN_2.5',
            libelle='Moins de 2,5 buts', probabilite=0.55,
            cote_juste=1.82, niveau='equilibree', origine='calcul',
        )

    def test_roundtrip(self):
        data = exporter_snapshot()
        self.assertEqual(len(data['matchs']), 1)
        self.assertEqual(data['matchs'][0]['sofascore_id'], 424242)
        self.assertIsNotNone(data['matchs'][0]['analyse'])

        Match.objects.all().delete()
        Equipe.objects.all().delete()
        Competition.objects.all().delete()

        stats = importer_snapshot(data)
        self.assertEqual(stats['matchs'], 1)
        self.assertEqual(stats['analyses'], 1)
        self.assertGreaterEqual(stats['options'], 1)
        m = Match.objects.get(sofascore_id=424242)
        self.assertEqual(m.domicile.slug, 'home-fc')
        self.assertTrue(hasattr(m, 'analyse'))
        self.assertEqual(m.analyse.options.count(), 1)
        # Logos navigateur : URL CDN embarquée (ESPN), pas de fallback tiers.
        from paris.clubs import logo_url_pour
        self.assertEqual(logo_url_pour(m.domicile), '')

    def test_import_reutilise_equipe_meme_nom_autre_sid(self):
        """Migration SofaScore → ESPN : même nom, nouvel id, slug différent."""
        Equipe.objects.create(
            nom='Arsenal', nom_court='Arsenal', slug='arsenal-old', sofascore_id=999001,
        )
        payload = {
            'version': 1,
            'competitions': [{
                'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                'ordre': 20, 'actif': True, 'sofascore_id': 700,
            }],
            'equipes': [
                {'nom': 'Arsenal', 'nom_court': 'Arsenal', 'slug': 'arsenal',
                 'sofascore_id': 359, 'logo_externe': '', 'fiche_club': {}},
                {'nom': 'Chelsea', 'nom_court': 'Chelsea', 'slug': 'chelsea',
                 'sofascore_id': 363, 'logo_externe': '', 'fiche_club': {}},
            ],
            'matchs': [{
                'sofascore_id': 401999001,
                'competition_code': 'PL',
                'domicile_slug': 'arsenal',
                'exterieur_slug': 'chelsea',
                'coup_denvoi': '2026-09-20T15:00:00+00:00',
                'statut': 'a_venir',
                'cotes': [],
                'analyse': None,
            }],
        }
        stats = importer_snapshot(payload)
        self.assertEqual(stats['equipes'], 2)
        self.assertEqual(stats['matchs'], 1)
        ars = Equipe.objects.get(slug='arsenal')
        self.assertEqual(ars.nom, 'Arsenal')
        self.assertEqual(ars.sofascore_id, 359)
        self.assertFalse(Equipe.objects.filter(nom='Arsenal').exclude(pk=ars.pk).exists())

    def test_import_reutilise_match_meme_fixture_autre_sid(self):
        """Ancien match SofaScore (autre sid) → réutilisé pour l’id ESPN."""
        Match.objects.all().delete()
        ancien = Match.objects.create(
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=datetime(2026, 9, 20, 15, 0, tzinfo=dt_timezone.utc),
            statut='a_venir',
            sofascore_id=111111,
        )
        payload = {
            'version': 1,
            'competitions': [{
                'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                'ordre': 20, 'actif': True, 'sofascore_id': 700,
            }],
            'equipes': [
                {'nom': 'Home FC', 'nom_court': 'Home', 'slug': 'home-fc',
                 'sofascore_id': 1, 'logo_externe': '', 'fiche_club': {}},
                {'nom': 'Away FC', 'nom_court': 'Away', 'slug': 'away-fc',
                 'sofascore_id': 2, 'logo_externe': '', 'fiche_club': {}},
            ],
            'matchs': [{
                'sofascore_id': 401888001,
                'competition_code': 'PL',
                'domicile_slug': 'home-fc',
                'exterieur_slug': 'away-fc',
                'coup_denvoi': '2026-09-20T15:00:00+00:00',
                'statut': 'a_venir',
                'cotes': [],
                'analyse': None,
            }],
        }
        stats = importer_snapshot(payload)
        self.assertEqual(stats['matchs'], 1)
        self.assertEqual(Match.objects.count(), 1)
        m = Match.objects.get()
        self.assertEqual(m.pk, ancien.pk)
        self.assertEqual(m.sofascore_id, 401888001)

    def test_import_fusionne_sid_espn_corrompu_et_ligne_correcte(self):
        """Bug V4 : ligne ESPN (mauvaises équipes) + ligne correcte → une seule.

        Sans fusion, le save de la ligne ESPN heurte
        UNIQUE(domicile, exterieur, coup_denvoi).
        """
        Match.objects.all().delete()
        wrong = Equipe.objects.create(
            nom='Wrong FC', nom_court='Wrong', slug='wrong-fc', sofascore_id=99,
        )
        coup = datetime(2026, 9, 20, 15, 0, tzinfo=dt_timezone.utc)
        corrompu = Match.objects.create(
            competition=self.comp,
            domicile=self.dom,
            exterieur=wrong,
            coup_denvoi=coup,
            statut='a_venir',
            sofascore_id=401915451,
        )
        correct = Match.objects.create(
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=coup,
            statut='a_venir',
            sofascore_id=111111,
        )
        payload = {
            'version': 1,
            'competitions': [{
                'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                'ordre': 20, 'actif': True, 'sofascore_id': None,
            }],
            'equipes': [
                {'nom': 'Home FC', 'nom_court': 'Home', 'slug': 'home-fc',
                 'sofascore_id': None, 'logo_externe': '', 'fiche_club': {}},
                {'nom': 'Away FC', 'nom_court': 'Away', 'slug': 'away-fc',
                 'sofascore_id': None, 'logo_externe': '', 'fiche_club': {}},
            ],
            'matchs': [{
                'sofascore_id': 401915451,
                'competition_code': 'PL',
                'domicile_slug': 'home-fc',
                'exterieur_slug': 'away-fc',
                'coup_denvoi': '2026-09-20T15:00:00+00:00',
                'statut': 'a_venir',
                'cotes': [],
                'analyse': None,
            }],
        }
        stats = importer_snapshot(payload)
        self.assertEqual(stats['matchs'], 1)
        self.assertEqual(Match.objects.count(), 1)
        m = Match.objects.get()
        self.assertEqual(m.pk, correct.pk)
        self.assertEqual(m.sofascore_id, 401915451)
        self.assertEqual(m.exterieur_id, self.ext.pk)
        self.assertFalse(Match.objects.filter(pk=corrompu.pk).exists())
        self.assertIsNone(Equipe.objects.get(slug='home-fc').sofascore_id)

    def test_import_fusionne_slugs_synonymes_alaves(self):
        """deportivo-alaves (V3) + alaves (V4) → une seule équipe, un seul match."""
        Match.objects.all().delete()
        Equipe.objects.all().delete()
        ancien = Equipe.objects.create(
            nom='Deportivo Alavés', nom_court='Alavés',
            slug='deportivo-alaves', sofascore_id=None,
        )
        bilbao = Equipe.objects.create(
            nom='Athletic Club', nom_court='Athletic',
            slug='athletic-bilbao', sofascore_id=None,
        )
        coup = datetime(2026, 9, 19, 14, 15, tzinfo=dt_timezone.utc)
        Match.objects.create(
            competition=self.comp, domicile=bilbao, exterieur=ancien,
            coup_denvoi=coup, statut='a_venir', sofascore_id=111000,
        )
        payload = {
            'version': 1,
            'competitions': [{
                'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                'ordre': 20, 'actif': True, 'sofascore_id': None,
            }],
            'equipes': [
                {'nom': 'Athletic Club', 'nom_court': 'Athletic',
                 'slug': 'athletic-bilbao', 'sofascore_id': None,
                 'logo_externe': '', 'fiche_club': {}},
                {'nom': 'Alavés', 'nom_court': 'Alavés', 'slug': 'alaves',
                 'sofascore_id': None, 'logo_externe': '', 'fiche_club': {}},
            ],
            'matchs': [{
                'sofascore_id': 401882866,
                'competition_code': 'PL',
                'domicile_slug': 'athletic-bilbao',
                'exterieur_slug': 'alaves',
                'coup_denvoi': '2026-09-19T14:15:00+00:00',
                'statut': 'a_venir',
                'cotes': [],
                'analyse': None,
            }],
        }
        importer_snapshot(payload)
        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(Equipe.objects.filter(slug__contains='alaves').count(), 1)
        m = Match.objects.get()
        self.assertEqual(m.sofascore_id, 401882866)
        self.assertEqual(m.exterieur.slug, 'alaves')
        self.assertFalse(Equipe.objects.filter(pk=ancien.pk, slug='deportivo-alaves').exists())

