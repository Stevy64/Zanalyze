"""Tests bilans passés + gamification Premium."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from paris.gamification import grade_pour, regler_pronostics_match
from paris.models import Competition, Equipe, Match, Option, Analyse, Profil, PronosticPremium
from paris.moteur import VERSION_MOTEUR


class BilanAccesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.comp = Competition.objects.create(
            code='PL', nom='Premier League', ordre=20, sofascore_id=700,
        )
        self.dom = Equipe.objects.create(
            nom='Home FC', nom_court='Home', slug='home-fc', sofascore_id=1,
        )
        self.ext = Equipe.objects.create(
            nom='Away FC', nom_court='Away', slug='away-fc', sofascore_id=2,
        )
        self.match = Match.objects.create(
            sofascore_id=424201,
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=timezone.now() - timedelta(days=1),
            statut='termine',
            buts_dom=2,
            buts_ext=1,
        )
        ana = Analyse.objects.create(
            match=self.match,
            buts_dom_attendus=1.4,
            buts_ext_attendus=1.1,
            p1=0.45, pn=0.28, p2=0.27,
            score_probable='1-1',
            profil='equilibre',
            marge_marche=0.05,
            residu=0.1,
            version_moteur=VERSION_MOTEUR,
        )
        for niveau, code, lib, res in (
            ('prudente', 'DC_1X', 'Home ne perd pas', 'gagne'),
            ('recommandee', '1X2_1', 'Home gagne', 'gagne'),
            ('filet', 'OU25_under', 'Moins de 2.5', 'perdu'),
            ('audacieuse', 'BTTS_yes', 'Les 2 marquent', 'gagne'),
        ):
            Option.objects.create(
                analyse=ana, niveau=niveau, code=code, libelle=lib,
                probabilite=0.55, famille='1X2', resultat=res,
                origine='marche', cote_juste=1.8,
            )

    def test_anonyme_ne_voit_que_prudente_filet(self):
        r = self.client.get(f'/api/v1/matchs/{self.match.id}/')
        self.assertEqual(r.status_code, 200)
        niveaux = {o['niveau'] for o in r.data['analyse']['options']}
        self.assertEqual(niveaux, {'prudente', 'filet'})
        self.assertFalse(r.data['bilan_complet'])

    def test_admin_voit_tout(self):
        admin = User.objects.create_user('adm', password='motdepasse123', is_staff=True)
        self.client.force_authenticate(admin)
        r = self.client.get(f'/api/v1/matchs/{self.match.id}/')
        self.assertEqual(r.status_code, 200)
        niveaux = {o['niveau'] for o in r.data['analyse']['options']}
        self.assertIn('recommandee', niveaux)
        self.assertTrue(r.data['bilan_complet'])

    def test_premium_voit_tout(self):
        u = User.objects.create_user('prem', password='motdepasse123')
        p, _ = Profil.objects.get_or_create(user=u)
        p.activer_vip(mois=1)
        p.save()
        self.client.force_authenticate(u)
        r = self.client.get(f'/api/v1/matchs/{self.match.id}/')
        self.assertEqual(r.status_code, 200)
        niveaux = {o['niveau'] for o in r.data['analyse']['options']}
        self.assertIn('recommandee', niveaux)
        self.assertIn('audacieuse', niveaux)
        self.assertTrue(r.data['bilan_complet'])


class GamificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.comp = Competition.objects.create(
            code='PL', nom='Premier League', ordre=20, sofascore_id=701,
        )
        self.dom = Equipe.objects.create(
            nom='A FC', nom_court='A', slug='a-fc', sofascore_id=11,
        )
        self.ext = Equipe.objects.create(
            nom='B FC', nom_court='B', slug='b-fc', sofascore_id=12,
        )
        self.match = Match.objects.create(
            sofascore_id=424202,
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=timezone.now() + timedelta(hours=3),
            statut='a_venir',
        )
        self.user = User.objects.create_user('premu', password='motdepasse123')
        p, _ = Profil.objects.get_or_create(user=self.user)
        p.activer_vip(mois=1)
        p.save()

    def test_pronostic_et_points(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(
            f'/api/v1/matchs/{self.match.id}/pronostic/',
            {'choix': '1'}, format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['choix'], '1')

        self.match.statut = 'termine'
        self.match.buts_dom = 2
        self.match.buts_ext = 0
        self.match.save()
        n = regler_pronostics_match(self.match)
        self.assertEqual(n, 1)
        p = Profil.objects.get(user=self.user)
        self.assertEqual(p.points_premium, 12)
        self.assertEqual(grade_pour(12), 'mougou')

        r2 = self.client.get('/api/v1/classement/')
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(any(x['username'] == 'premu' for x in r2.data['results']))
        self.assertIn('objectif', r2.data['moi'])
        self.assertIn('stats', r2.data['moi'])

    def test_membre_peut_pronostiquer(self):
        membre = User.objects.create_user('membre_g', password='motdepasse123')
        Profil.objects.get_or_create(user=membre, defaults={'categorie': 'membre'})
        self.client.force_authenticate(membre)
        r = self.client.post(
            f'/api/v1/matchs/{self.match.id}/pronostic/',
            {'choix': 'N'}, format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['choix'], 'N')
        self.assertIn('progression', r.data)
