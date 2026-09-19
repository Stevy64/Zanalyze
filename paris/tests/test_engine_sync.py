"""Tests sync snapshot Engine → PWA."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from paris import engine_sync


class EngineSyncApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self._tmpdir = tempfile.TemporaryDirectory()
        self._meta = Path(self._tmpdir.name) / 'engine_sync.json'
        self._patcher = patch.object(engine_sync, '_meta_path', return_value=self._meta)
        self._patcher.start()
        if engine_sync._lock.locked():
            try:
                engine_sync._lock.release()
            except RuntimeError:
                pass
        engine_sync._async_started = False

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_etat_sync_get(self):
        r = self.client.get('/api/v1/sync/engine/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('url', r.data)

    def test_version_moteur_active_depuis_meta(self):
        engine_sync._ecrire_meta({'version_moteur': '4.0.0', 'ok': True})
        self.assertEqual(engine_sync.version_moteur_active(), '4.0.0')
        r = self.client.get('/api/v1/info/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['version_moteur'], '4.0.0')

    def test_version_depuis_snapshot(self):
        v = engine_sync._version_depuis_snapshot({
            'matchs': [{'analyse': {'version_moteur': '4.0.0'}}],
        })
        self.assertEqual(v, '4.0.0')

    @override_settings(
        ZANALYZ_SNAPSHOT_URL='https://example.test/matchs.json',
    )
    def test_sync_post_throttle_puis_import(self):
        payload = {
            'version': 1,
            'exporte_le': '2026-09-16T00:00:00+00:00',
            'competitions': [],
            'equipes': [],
            'matchs': [],
        }
        with patch.object(engine_sync, 'telecharger_snapshot', return_value=(payload, 'abc')):
            with patch('paris.snapshot.importer_snapshot', return_value={'matchs': 0}) as imp:
                r1 = self.client.post('/api/v1/sync/engine/', {'force': True}, format='json')
                self.assertEqual(r1.status_code, 200, r1.data)
                self.assertTrue(r1.data.get('ok'), r1.data)
                self.assertFalse(r1.data.get('skipped'), r1.data)
                imp.assert_called_once()

                r2 = self.client.post('/api/v1/sync/engine/', {'force': True}, format='json')
                self.assertEqual(r2.status_code, 200)
                self.assertTrue(r2.data.get('skipped'))
                self.assertEqual(r2.data.get('reason'), 'trop_recent')

    def test_info_contient_engine(self):
        with patch.object(engine_sync, 'declencher_refresh_async', return_value=False):
            r = self.client.get('/api/v1/info/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('engine', r.data)
