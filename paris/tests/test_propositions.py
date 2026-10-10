"""Tests propositions utilisateurs + consensus."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from paris.models import Competition, Equipe, Match, Profil, PropositionParis


class PropositionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.comp = Competition.objects.create(code='PL', nom='Premier League', ordre=1)
        self.dom = Equipe.objects.create(nom='Home FC', nom_court='Home', slug='home-fc')
        self.ext = Equipe.objects.create(nom='Away FC', nom_court='Away', slug='away-fc')
        self.match = Match.objects.create(
            competition=self.comp,
            domicile=self.dom,
            exterieur=self.ext,
            coup_denvoi=timezone.now() + timedelta(hours=2),
        )
        self.u1 = User.objects.create_user('prop1', password='motdepasse123')
        self.u2 = User.objects.create_user('prop2', password='motdepasse123')
        Profil.objects.get_or_create(user=self.u1)
        Profil.objects.get_or_create(user=self.u2)

    def test_publier_et_lister(self):
        self.client.force_authenticate(self.u1)
        r = self.client.post(
            f'/api/v1/matchs/{self.match.id}/propositions/',
            {'type': 'plus_25', 'confiance': 89},
            format='json',
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['libelle'], 'Plus de 2,5 buts')
        self.assertEqual(r.data['confiance'], 89)
        self.assertIn('consensus', r.data)

        r2 = self.client.get(f'/api/v1/matchs/{self.match.id}/propositions/')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.data['results']), 1)
        self.assertEqual(r2.data['consensus']['total'], 1)
        self.assertEqual(r2.data['consensus']['par_option'][0]['pct'], 100)

    def test_une_proposition_par_user(self):
        self.client.force_authenticate(self.u1)
        url = f'/api/v1/matchs/{self.match.id}/propositions/'
        self.client.post(url, {'type': 'plus_25', 'confiance': 70}, format='json')
        r = self.client.post(url, {'type': 'moins_25', 'confiance': 55}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(PropositionParis.objects.filter(match=self.match, auteur=self.u1).count(), 1)
        self.assertEqual(r.data['libelle'], 'Moins de 2,5 buts')

    def test_consensus_plusieurs_users(self):
        self.client.force_authenticate(self.u1)
        self.client.post(
            f'/api/v1/matchs/{self.match.id}/propositions/',
            {'type': 'vainqueur_dom', 'confiance': 60},
            format='json',
        )
        self.client.force_authenticate(self.u2)
        self.client.post(
            f'/api/v1/matchs/{self.match.id}/propositions/',
            {'type': 'vainqueur_dom', 'confiance': 80},
            format='json',
        )
        r = self.client.get(f'/api/v1/matchs/{self.match.id}/propositions/')
        self.assertEqual(r.data['consensus']['total'], 2)
        top = r.data['consensus']['par_option'][0]
        self.assertEqual(top['type'], 'vainqueur_dom')
        self.assertEqual(top['pct'], 100)
        self.assertEqual(top['n'], 2)
