"""Historique abonnements Premium + message WhatsApp renouvellement."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from urllib.parse import unquote

from paris.models import HistoriqueAbonnement, Profil, ReglageSite


class HistoriqueAbonnementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'a@z.test', 'x')
        self.user = User.objects.create_user('ZanBeta', password='x')
        self.profil, _ = Profil.objects.get_or_create(user=self.user)

    def test_premier_puis_renouvellement(self):
        self.assertEqual(self.profil.premium_acceptations, 0)
        self.assertFalse(self.profil.a_deja_ete_premium)

        self.profil.activer_vip(mois=1)
        self.profil.enregistrer_acceptation_premium(
            type_evt='premier', mois=1, admin_user=self.admin,
        )
        self.profil.save()
        self.assertEqual(self.profil.premium_acceptations, 1)
        self.assertEqual(self.profil.libelle_cycle_premium, '1er abonnement')
        self.assertEqual(HistoriqueAbonnement.objects.filter(profil=self.profil).count(), 1)

        self.profil.activer_vip(mois=1)
        self.profil.enregistrer_acceptation_premium(
            type_evt='renouvellement', mois=1, admin_user=self.admin,
        )
        self.profil.save()
        self.assertEqual(self.profil.premium_acceptations, 2)
        self.assertEqual(
            self.profil.libelle_cycle_premium,
            'Renouvellement n°1 (cycle 2)',
        )
        hist = HistoriqueAbonnement.objects.filter(profil=self.profil).order_by('ordre')
        self.assertEqual(list(hist.values_list('type', flat=True)), [
            'premier', 'renouvellement',
        ])


class WhatsappRenouvellementTests(TestCase):
    def setUp(self):
        cfg = ReglageSite.get_solo()
        cfg.whatsapp_phone = '24106000000'
        cfg.whatsapp_url = ''
        cfg.whatsapp_message = (
            'Bonjour, je suis {pseudo}, Zanalyste sur Zanalyze. '
            'Je souhaite devenir Premium.'
        )
        cfg.save()

    def test_premiere_demande(self):
        user = User.objects.create_user('NouveauZan', password='x')
        Profil.objects.get_or_create(user=user)
        client = APIClient()
        client.force_authenticate(user=user)
        r = client.get('/api/v1/info/')
        url = unquote(r.data.get('whatsapp_vip_url') or '')
        self.assertIn('devenir Premium', url)
        self.assertNotIn('renouveler mon abonnement Premium', url)
        self.assertFalse(r.data.get('premium_renouvellement'))

    def test_demande_apres_acceptation(self):
        user = User.objects.create_user('AncienZan', password='x')
        profil, _ = Profil.objects.get_or_create(user=user)
        profil.vip_depuis = timezone.now()
        profil.premium_acceptations = 1
        profil.save()
        client = APIClient()
        client.force_authenticate(user=user)
        r = client.get('/api/v1/info/')
        url = unquote(r.data.get('whatsapp_vip_url') or '')
        self.assertIn('renouveler mon abonnement Premium', url)
        self.assertNotIn('devenir Premium', url)
        self.assertTrue(r.data.get('premium_renouvellement'))
        self.assertIn('AncienZan', url)
