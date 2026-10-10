from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from paris.models import PaiementPremium, Profil, ReglageSite
from paris.premium_paiement import verifier_et_activer


class PremiumPaiementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('payer', password='password123')
        self.other = User.objects.create_user('other', password='password123')
        self.client.force_authenticate(self.user)
        cfg = ReglageSite.get_solo()
        cfg.vip_prix_xaf = 2500
        cfg.save(update_fields=['vip_prix_xaf'])

    def test_checkout_refuse_sans_tarif_ou_identifiants(self):
        response = self.client.post('/api/v1/premium/checkout/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(PaiementPremium.objects.count(), 0)

    @patch('paris.premium_paiement.configuration')
    @patch('paris.premium_paiement._appel')
    def test_activation_exacte_et_idempotente(self, appel, configuration):
        configuration.return_value = {'wallet': 'wallet-test'}
        achat = PaiementPremium.objects.create(user=self.user, montant_xaf=2500)
        payload = {'reference': str(achat.reference), 'amount': 2500,
                   'portefeuille': 'wallet-test', 'status': 'Terminate',
                   'result': 'Success', 'id': 'tx-test'}
        appel.return_value = payload
        self.assertEqual(verifier_et_activer(achat), 'paye')
        profil = Profil.objects.get(user=self.user)
        expiration = profil.vip_expire_le
        self.assertTrue(profil.abonnement_vip_actif)
        self.assertEqual(verifier_et_activer(achat), 'paye')
        profil.refresh_from_db()
        self.assertEqual(profil.vip_expire_le, expiration)
        self.assertEqual(profil.premium_acceptations, 1)

    @patch('paris.premium_paiement.configuration')
    @patch('paris.premium_paiement._appel')
    def test_montant_inexact_ne_donne_aucun_acces(self, appel, configuration):
        configuration.return_value = {'wallet': 'wallet-test'}
        achat = PaiementPremium.objects.create(user=self.user, montant_xaf=2500)
        appel.return_value = {'reference': str(achat.reference), 'amount': 250,
                              'portefeuille': 'wallet-test', 'status': 'Terminate',
                              'result': 'Success'}
        self.assertNotEqual(verifier_et_activer(achat), 'paye')
        self.assertFalse(Profil.objects.filter(user=self.user, categorie='premium').exists())

    def test_un_membre_ne_peut_pas_verifier_le_paiement_d_un_autre(self):
        achat = PaiementPremium.objects.create(user=self.other, montant_xaf=2500)
        response = self.client.get(f'/api/v1/premium/paiements/{achat.reference}/')
        self.assertEqual(response.status_code, 404)
