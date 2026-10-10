"""Env de test avant chargement Django (pytest-django)."""
import os

os.environ.setdefault(
    'DJANGO_SECRET_KEY',
    'ci-test-secret-key-not-for-production-use-please-rotate-locally-xx',
)
os.environ.setdefault('DJANGO_DEBUG', '0')
os.environ.setdefault('DJANGO_SSL', '0')
os.environ.setdefault('DJANGO_SECURE_SSL_REDIRECT', '0')
os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')

# Aucun import automatique ni requête réseau pendant les tests.
os.environ.setdefault('ZANALYZ_SYNC_LIVE', '0')
