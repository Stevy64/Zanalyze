from django.test import TestCase
from django.utils import timezone

from paris.models import Analyse, Competition, Equipe, Match, Option


def _base():
    comp = Competition.objects.create(code='UCL', nom='Ligue des champions', ordre=1)
    a = Equipe.objects.create(nom='PSG', nom_court='PSG', slug='psg')
    b = Equipe.objects.create(nom='Bayern', nom_court='Bayern', slug='bayern')
    return comp, a, b


class ApiMatchsQueriesTests(TestCase):
    def setUp(self):
        comp, d, e = _base()
        now = timezone.now()
        for i in range(5):
            ext = Equipe.objects.create(
                nom=f'Club {i}', nom_court=f'C{i}', slug=f'club-{i}',
            )
            m = Match.objects.create(
                competition=comp, domicile=d, exterieur=ext,
                coup_denvoi=now, journee='J1',
                sofascore_id=900000 + i,
            )
            an = Analyse.objects.create(
                match=m,
                buts_dom_attendus=1.4, buts_ext_attendus=1.1,
                p1=0.45, pn=0.28, p2=0.27,
                score_probable='1-1', profil='equilibre',
                marge_marche=0.05, residu=0.01,
                version_moteur='1.0.0',
            )
            for niv, code, lib, p in (
                ('prudente', 'OV_1.5', 'Au moins 2 buts', 0.78),
                ('equilibree', 'DC_1X', 'PSG ne perd pas', 0.62),
                ('audacieuse', 'UN_2.5', 'Moins de 2,5 buts', 0.40),
                ('filet', 'OV_0.5', 'Au moins 1 but', 0.93),
                ('detail', '1X2_1', 'PSG gagne', 0.45),
            ):
                Option.objects.create(
                    analyse=an, famille='Total buts', code=code,
                    libelle=lib, probabilite=p, cote_juste=1 / p,
                    niveau=niv, origine='calcul',
                )

    def test_filtre_pays(self):
        liga = Competition.objects.create(
            code='LIGA', nom='LaLiga', pays='Espagne', ordre=30,
        )
        d = Equipe.objects.get(slug='psg')
        e = Equipe.objects.create(nom='Barça', nom_court='Barça', slug='barca-test')
        Match.objects.create(
            competition=liga, domicile=d, exterieur=e,
            coup_denvoi=timezone.now(), journee='J1', sofascore_id=900099,
        )
        r = self.client.get('/api/v1/matchs/', {'pays': 'Espagne'})
        self.assertEqual(r.status_code, 200)
        codes = {row['competition']['code'] for row in r.json()['results']}
        self.assertEqual(codes, {'LIGA'})
        self.assertTrue(all(row['competition']['pays'] == 'Espagne' for row in r.json()['results']))

    def test_liste_moins_de_six_requetes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get('/api/v1/matchs/')
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries), 6,
            '\n'.join(q['sql'] for q in ctx.captured_queries),
        )

    def test_liste_legere_et_cache(self):
        r = self.client.get('/api/v1/matchs/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('ETag', r)
        self.assertIn('max-age=300', r['Cache-Control'])
        self.assertLess(len(r.content), 40_000)
        data = r.json()
        row = data['results'][0]
        self.assertNotIn('contexte', row)
        self.assertIn('libelle', row['options'][0])
        self.assertIn('probabilite', row['options'][0])
        niveaux = {o['niveau'] for o in row['options']}
        self.assertTrue(niveaux <= {'prudente', 'recommandee', 'equilibree', 'audacieuse', 'filet'})
        self.assertGreaterEqual(len(row['options']), 3)
        self.assertLessEqual(len(row['options']), 4)

    def test_fiche_complete(self):
        m = Match.objects.first()
        r = self.client.get(f'/api/v1/matchs/{m.pk}/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('analyse', body)
        self.assertGreater(len(body['analyse']['options']), 3)

    def test_resultat_refuse_anonyme(self):
        m = Match.objects.first()
        r = self.client.post(
            f'/api/v1/matchs/{m.pk}/resultat/',
            {'buts_dom': 2, 'buts_ext': 1},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)

    def test_resultat_regle_les_options(self):
        from django.contrib.auth.models import User
        staff = User.objects.create_user('admin', password='x' * 12, is_staff=True)
        self.client.force_login(staff)
        m = Match.objects.first()
        r = self.client.post(
            f'/api/v1/matchs/{m.pk}/resultat/',
            {'buts_dom': 2, 'buts_ext': 1},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.statut, 'termine')
        self.assertEqual(m.score, '2-1')
        self.assertTrue(
            m.analyse.options.exclude(resultat='attente').exists()
        )


class VerificationEchantillonTests(TestCase):
    def test_trop_petit(self):
        r = self.client.get('/api/v1/verification/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['par_niveau']['prudente']['echantillon_trop_petit'])
        self.assertIsNone(data['par_niveau']['prudente']['taux'])
