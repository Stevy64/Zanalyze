"""Tests VIP + Salon VIP 24 h."""

from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from paris.chat import messages_actifs, purger_messages_expires
from paris.models import MSG_DEMANDE_PREMIUM, MessageChat, Profil, ReglageSite
from paris.roles import categorie_user, est_vip, payload_auth
from paris.vip import ajouter_mois


class RolesVipTests(TestCase):
    def test_vip_et_premium_normalises(self):
        u = User.objects.create_user('vipuser', password='motdepasse123')
        profil, _ = Profil.objects.get_or_create(user=u)
        profil.activer_vip(mois=1)
        profil.save()
        self.assertEqual(categorie_user(u), 'premium')
        self.assertTrue(est_vip(u))

        profil.categorie = 'premium'
        profil.vip_expire_le = timezone.now() + timedelta(days=10)
        profil.save(update_fields=['categorie', 'vip_expire_le'])
        self.assertEqual(categorie_user(u), 'premium')
        self.assertTrue(est_vip(u))

        profil.categorie = 'membre'
        profil.save(update_fields=['categorie'])
        self.assertEqual(categorie_user(u), 'membre')
        self.assertFalse(est_vip(u))

    def test_vip_expire_apres_un_mois(self):
        u = User.objects.create_user('expire1', password='motdepasse123')
        profil, _ = Profil.objects.get_or_create(user=u)
        profil.activer_vip(mois=1)
        profil.save()
        self.assertTrue(est_vip(u))
        self.assertEqual(profil.vip_expire_le, ajouter_mois(profil.vip_depuis, 1))

        profil.vip_expire_le = timezone.now() - timedelta(seconds=1)
        profil.save(update_fields=['vip_expire_le'])
        self.assertFalse(est_vip(u))
        self.assertEqual(categorie_user(u), 'membre')
        payload = payload_auth(u)
        self.assertFalse(payload['est_vip'])

    def test_prolonger_ajoute_un_mois(self):
        u = User.objects.create_user('prolonge1', password='motdepasse123')
        profil, _ = Profil.objects.get_or_create(user=u)
        profil.activer_vip(mois=1)
        profil.save()
        fin1 = profil.vip_expire_le
        profil.prolonger_vip(mois=1)
        profil.save()
        self.assertEqual(profil.vip_expire_le, ajouter_mois(fin1, 1))
        self.assertTrue(est_vip(u))

    def test_staff_et_superuser_sont_premium(self):
        staff = User.objects.create_user('adminstaff', password='motdepasse123', is_staff=True)
        self.assertEqual(categorie_user(staff), 'premium')
        self.assertTrue(est_vip(staff))
        payload = payload_auth(staff)
        self.assertTrue(payload['est_vip'])
        self.assertTrue(payload['est_premium'])
        self.assertTrue(payload['est_admin'])

        su = User.objects.create_superuser('rootadmin', 'root@example.com', 'motdepasse123')
        self.assertEqual(categorie_user(su), 'premium')
        self.assertTrue(est_vip(su))


class SalonVipTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.membre = User.objects.create_user('membre1', password='motdepasse123')
        Profil.objects.get_or_create(user=self.membre, defaults={'categorie': 'membre'})
        self.vip = User.objects.create_user('vip1', password='motdepasse123')
        p, _ = Profil.objects.get_or_create(user=self.vip)
        p.activer_vip(mois=1)
        p.save()

    def test_salon_exige_auth(self):
        r = self.client.get('/api/v1/salon/')
        self.assertIn(r.status_code, (401, 403))

    def test_membre_refuse(self):
        self.client.force_authenticate(self.membre)
        r = self.client.get('/api/v1/salon/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data.get('code'), 'vip_required')

    def test_vip_expire_refuse_salon(self):
        p = self.vip.profil
        p.vip_expire_le = timezone.now() - timedelta(hours=1)
        p.save(update_fields=['vip_expire_le'])
        self.client.force_authenticate(self.vip)
        r = self.client.get('/api/v1/salon/')
        self.assertEqual(r.status_code, 403)

    def test_vip_post_et_liste(self):
        self.client.force_authenticate(self.vip)
        r = self.client.post('/api/v1/salon/', {'texte': 'Salut les VIP'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['texte'], 'Salut les VIP')
        self.assertTrue(r.data['est_moi'])
        self.assertIsNone(r.data.get('image_url'))

        r2 = self.client.get('/api/v1/salon/')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.data['results']), 1)

    def test_vip_post_image(self):
        self.client.force_authenticate(self.vip)
        # PNG 1x1 minimal
        png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
            b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
            b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        image = SimpleUploadedFile('shot.png', png, content_type='image/png')
        r = self.client.post(
            '/api/v1/salon/',
            {'texte': 'Capture', 'image': image},
            format='multipart',
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['texte'], 'Capture')
        self.assertTrue(r.data.get('image_url'))
        msg = MessageChat.objects.get(pk=r.data['id'])
        self.assertTrue(msg.image)

    def test_vip_post_image_seule(self):
        self.client.force_authenticate(self.vip)
        png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
            b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
            b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        image = SimpleUploadedFile('solo.png', BytesIO(png).read(), content_type='image/png')
        r = self.client.post('/api/v1/salon/', {'image': image}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['texte'], '')
        self.assertTrue(r.data.get('image_url'))

    def test_purge_apres_24h(self):
        ancien = MessageChat.objects.create(auteur=self.vip, texte='vieux')
        MessageChat.objects.filter(pk=ancien.pk).update(
            created_at=timezone.now() - timedelta(hours=25),
        )
        MessageChat.objects.create(auteur=self.vip, texte='frais')
        n = purger_messages_expires()
        self.assertGreaterEqual(n, 1)
        self.assertEqual(messages_actifs().count(), 1)
        self.assertEqual(messages_actifs().first().texte, 'frais')


class InfoWhatsappTests(TestCase):
    def test_info_expose_lien_whatsapp(self):
        cfg = ReglageSite.get_solo()
        cfg.whatsapp_phone = '33612345678'
        cfg.whatsapp_message = 'Bonjour VIP'
        cfg.whatsapp_url = ''
        cfg.vip_tarif_libelle = 'VIP — test'
        cfg.save()
        client = APIClient()
        r = client.get('/api/v1/info/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('wa.me/33612345678', r.data.get('whatsapp_vip_url', ''))
        self.assertEqual(r.data.get('vip_tarif_libelle'), 'VIP — test')

    def test_lien_whatsapp_inclut_pseudo_zanalyste(self):
        from django.contrib.auth import get_user_model
        from urllib.parse import unquote

        User = get_user_model()
        user = User.objects.create_user('Stevy64', password='x')
        cfg = ReglageSite.get_solo()
        cfg.whatsapp_phone = '24106123456'
        cfg.whatsapp_message = (
            'Bonjour, je suis {pseudo}, Zanalyste sur Zanalyze. '
            'Je souhaite devenir Premium.'
        )
        cfg.whatsapp_url = ''
        cfg.save()

        client = APIClient()
        client.force_authenticate(user=user)
        r = client.get('/api/v1/info/')
        self.assertEqual(r.status_code, 200)
        url = unquote(r.data.get('whatsapp_vip_url') or '')
        self.assertIn('wa.me/24106123456', url)
        self.assertIn('Stevy64', url)
        self.assertIn('Zanalyste', url)
        self.assertIn('Zanalyze', url)
        self.assertNotIn('Cleared2Bet', url)

    def test_whatsapp_url_statique_ne_bloque_pas_le_pseudo(self):
        from django.contrib.auth import get_user_model
        from urllib.parse import unquote

        User = get_user_model()
        user = User.objects.create_user('ZanAlpha', password='x')
        cfg = ReglageSite.get_solo()
        # Contourne save() pour simuler l’ancien enregistrement admin figé.
        ReglageSite.objects.filter(pk=cfg.pk).update(
            whatsapp_phone='',
            whatsapp_url='https://wa.me/33600000000?text=Bonjour%20Cleared2Bet',
            whatsapp_message=(
                'Bonjour, je suis {pseudo}, Zanalyste sur Zanalyze. '
                'Je souhaite devenir Premium.'
            ),
        )

        client = APIClient()
        client.force_authenticate(user=user)
        r = client.get('/api/v1/info/')
        url = unquote(r.data.get('whatsapp_vip_url') or '')
        self.assertIn('wa.me/33600000000', url)
        self.assertIn('ZanAlpha', url)
        self.assertNotIn('Cleared2Bet', url)

    def test_save_nettoie_ancien_whatsapp_url_admin(self):
        cfg = ReglageSite.get_solo()
        cfg.whatsapp_phone = ''
        cfg.whatsapp_url = (
            'https://wa.me/24106111111?text=Bonjour%20je%20veux%20Cleared2Bet'
        )
        cfg.whatsapp_message = MSG_DEMANDE_PREMIUM
        cfg.save()
        cfg.refresh_from_db()
        self.assertEqual(cfg.whatsapp_phone, '24106111111')
        self.assertEqual(cfg.whatsapp_url, 'https://wa.me/24106111111')
        self.assertNotIn('Cleared2Bet', cfg.whatsapp_url)
        self.assertNotIn('text=', cfg.whatsapp_url)