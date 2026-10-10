"""Présence Salon VIP (heartbeat Redis, TTL court)."""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_PREFIX = 'c2b:salon:online:'
_TTL = 120  # secondes — le client poll toutes les ~8–12 s


def _client():
    url = (getattr(settings, 'ZANALYZ_REDIS_URL', '') or '').strip()
    if not url:
        return None
    try:
        import redis
        return redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
    except Exception:  # noqa: BLE001
        return None


def marquer_en_ligne(user_id: int) -> None:
    if not user_id:
        return
    r = _client()
    if r is None:
        return
    try:
        r.set(f'{_PREFIX}{int(user_id)}', '1', ex=_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.debug('presence set: %s', exc)


def compter_en_ligne() -> int:
    r = _client()
    if r is None:
        return 0
    try:
        n = 0
        for _ in r.scan_iter(match=f'{_PREFIX}*', count=100):
            n += 1
        return n
    except Exception as exc:  # noqa: BLE001
        logger.debug('presence count: %s', exc)
        return 0
