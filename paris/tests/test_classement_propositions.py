from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from paris.models import Competition, Equipe, Match, PropositionParis


class ClassementPropositionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.comp = Competition.objects.create(code='TEST', nom='Test', ordre=1)
        self.home = Equipe.objects.create(nom='Home', nom_court='Home', slug='ranking-home')
        self.away = Equipe.objects.create(nom='Away', nom_court='Away', slug='ranking-away')
        self.good = User.objects.create_user('good', password='password123')
        self.one = User.objects.create_user('one', password='password123')

    def _match(self, index):
        return Match.objects.create(
            competition=self.comp, domicile=self.home, exterieur=self.away,
            coup_denvoi=timezone.now() - timedelta(days=index + 1),
            statut='termine', buts_dom=2, buts_ext=1,
        )

    def _prop(self, match, user, label, late=False):
        prop = PropositionParis.objects.create(match=match, auteur=user, libelle=label)
        date = match.coup_denvoi + timedelta(minutes=1) if late else match.coup_denvoi - timedelta(hours=1)
        PropositionParis.objects.filter(pk=prop.pk).update(created_at=date)
        return PropositionParis.objects.select_related('match').get(pk=prop.pk)

    def test_classement_exige_cinq_resultats_et_exclut_publication_tardive(self):
        for i in range(5):
            self._prop(self._match(i), self.good, 'Vainqueur domicile')
        self._prop(self._match(6), self.one, 'Vainqueur domicile')
        self._prop(self._match(7), self.one, 'Vainqueur domicile', late=True)
        response = self.client.get('/api/v1/classement/propositions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['username'] for r in response.data['results']], ['good'])
        self.assertEqual(response.data['results'][0]['valides'], 5)
        self.client.force_authenticate(self.one)
        mine = self.client.get('/api/v1/classement/propositions/').data['moi']
        self.assertEqual(mine['total'], 1)
        self.assertEqual(mine['restants'], 4)

    def test_resultat_serialise_et_creation_fermee_apres_coup_envoi(self):
        match = self._match(1)
        prop = self._prop(match, self.good, 'Plus de 2,5 buts')
        from paris.serializers import PropositionSerializer
        prop.likes = 0
        prop.dislikes = 0
        self.assertEqual(PropositionSerializer(prop).data['resultat'], 'valide')
        self.client.force_authenticate(self.one)
        response = self.client.post(f'/api/v1/matchs/{match.pk}/propositions/',
                                    {'type': 'vainqueur_dom'}, format='json')
        self.assertEqual(response.status_code, 400)
