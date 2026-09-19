"""Synchronisation PWA ← snapshot Zanalyze Engine (GitHub Actions).

L’app Django ne scrape pas ESPN elle-même en prod (souvent bloqué) :
elle importe le JSON produit par le moteur. Ce module centralise
téléchargement, throttle, et métadonnées de fraîcheur.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import urllib.request
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

DEFAULT_ENGINE_URL = (
    'https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json'
)
# Intervalle mini entre deux imports auto (force=False).
MIN_AGE_AUTO = 10 * 60
# Intervalle mini même avec force (anti-spam depuis le client).
MIN_AGE_FORCE = 90

_lock = threading.Lock()
_async_started = False


def snapshot_url() -> str:
    return (getattr(settings, 'ZANALYZ_SNAPSHOT_URL', None) or '').strip() or DEFAULT_ENGINE_URL


def _meta_path() -> Path:
    base = Path(settings.BASE_DIR) / 'data'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'engine_sync.json'


def lire_meta() -> dict[str, Any]:
    path = _meta_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _ecrire_meta(meta: dict[str, Any]) -> None:
    path = _meta_path()
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def etat_sync() -> dict[str, Any]:
    meta = lire_meta()
    return {
        'url': snapshot_url(),
        'exporte_le': meta.get('exporte_le'),
        'importe_le': meta.get('importe_le'),
        'content_hash': meta.get('content_hash'),
        'matchs': meta.get('matchs'),
        'version_moteur': meta.get('version_moteur') or version_moteur_active(),
        'dernier_ok': meta.get('ok'),
        'dernier_detail': meta.get('detail'),
    }


def _version_depuis_snapshot(data: dict[str, Any]) -> str | None:
    """Lit la version embarquée dans les analyses du snapshot Engine."""
    for m in data.get('matchs') or []:
        ana = m.get('analyse') or {}
        v = (ana.get('version_moteur') or '').strip()
        if v:
            return v[:12]
    return None


def version_moteur_active() -> str:
    """Version réellement active : meta d'import, sinon analyses en base, sinon constante locale."""
    meta = lire_meta()
    v = (meta.get('version_moteur') or '').strip()
    if v:
        return v[:12]
    try:
        from django.db.models import Count
        from paris.models import Analyse

        row = (
            Analyse.objects.exclude(version_moteur='')
            .values('version_moteur')
            .annotate(n=Count('id'))
            .order_by('-n', '-version_moteur')
            .first()
        )
        if row and row.get('version_moteur'):
            return str(row['version_moteur'])[:12]
    except Exception:  # noqa: BLE001 — base pas prête / migrations
        pass
    from paris.moteur import VERSION_MOTEUR
    return VERSION_MOTEUR


def _age_secondes(iso: str | None) -> float | None:
    if not iso:
        return None
    dt = parse_datetime(iso)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return (timezone.now() - dt).total_seconds()


def telecharger_snapshot(url: str, *, timeout: int = 45) -> tuple[dict[str, Any], str]:
    """Retourne (payload, sha256 hex du corps brut)."""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Zanalyze-PWA/1.0 (engine-sync)',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache',
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict) or 'matchs' not in data:
        raise ValueError('Snapshot invalide (clé matchs absente).')
    return data, digest


def importer_engine(*, force: bool = False, min_age: int | None = None) -> dict[str, Any]:
    """
    Télécharge et importe le snapshot Engine si nécessaire.
    Thread-safe. Ne lève pas : renvoie {ok, skipped, ...}.
    """
    url = snapshot_url()
    meta = lire_meta()
    age = _age_secondes(meta.get('importe_le'))
    seuil = MIN_AGE_FORCE if force else (MIN_AGE_AUTO if min_age is None else int(min_age))

    if age is not None and age < seuil:
        return {
            'ok': True,
            'skipped': True,
            'reason': 'trop_recent',
            'age_s': int(age),
            'min_age_s': seuil,
            **etat_sync(),
        }

    if not _lock.acquire(blocking=False):
        return {
            'ok': True,
            'skipped': True,
            'reason': 'deja_en_cours',
            **etat_sync(),
        }

    try:
        # Re-check under lock
        meta = lire_meta()
        age = _age_secondes(meta.get('importe_le'))
        if age is not None and age < seuil and not force:
            return {
                'ok': True,
                'skipped': True,
                'reason': 'trop_recent',
                'age_s': int(age),
                **etat_sync(),
            }

        data, digest = telecharger_snapshot(url)
        if digest == meta.get('content_hash') and not force:
            now = timezone.now().isoformat()
            meta['importe_le'] = now  # horloge touchée : on a vérifié la source
            meta['ok'] = True
            meta['detail'] = 'hash_inchange'
            v = _version_depuis_snapshot(data)
            if v:
                meta['version_moteur'] = v
            _ecrire_meta(meta)
            return {
                'ok': True,
                'skipped': True,
                'reason': 'hash_inchange',
                'exporte_le': data.get('exporte_le'),
                **etat_sync(),
            }

        from paris.snapshot import importer_snapshot

        stats = importer_snapshot(data)
        now = timezone.now().isoformat()
        version = _version_depuis_snapshot(data) or version_moteur_active()
        nouveau = {
            'url': url,
            'exporte_le': data.get('exporte_le'),
            'importe_le': now,
            'content_hash': digest,
            'matchs': len(data.get('matchs') or []),
            'version_moteur': version,
            'stats': stats,
            'ok': True,
            'detail': 'importe',
        }
        _ecrire_meta(nouveau)
        return {
            'ok': True,
            'skipped': False,
            'reason': 'importe',
            'stats': stats,
            'exporte_le': data.get('exporte_le'),
            'importe_le': now,
            'matchs': nouveau['matchs'],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning('Import Engine échoué : %s', exc)
        meta = lire_meta()
        meta.update({
            'ok': False,
            'detail': str(exc)[:300],
            'importe_le_echec': timezone.now().isoformat(),
        })
        try:
            _ecrire_meta(meta)
        except OSError:
            pass
        return {
            'ok': False,
            'skipped': False,
            'reason': 'erreur',
            'detail': str(exc)[:300],
            **etat_sync(),
        }
    finally:
        _lock.release()


def declencher_refresh_async(*, force: bool = False) -> bool:
    """Lance un import en arrière-plan si le snapshot semble périmé."""
    global _async_started
    meta = lire_meta()
    age = _age_secondes(meta.get('importe_le'))
    if not force and age is not None and age < MIN_AGE_AUTO:
        return False

    def _run():
        global _async_started
        try:
            importer_engine(force=force)
        finally:
            _async_started = False

    with _lock:
        # Ne pas bloquer si import déjà en cours (lock tenu ailleurs).
        pass
    if _async_started:
        return False
    _async_started = True
    threading.Thread(target=_run, daemon=True, name='engine-sync').start()
    return True
