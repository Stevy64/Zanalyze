"""Client du microservice moteur (même paquet local si ZANALYZ_MOTEUR_URL vide)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from engine.moteur import AnalyseInvalide, VERSION_MOTEUR
from engine.api_analyse import AnalyserRequest, post_analyser
from fastapi import HTTPException
from pydantic import ValidationError


def _moteur_url() -> str:
    return (getattr(settings, 'ZANALYZ_MOTEUR_URL', None) or '').rstrip('/')


def moteur_disponible() -> bool:
    base = _moteur_url()
    if not base:
        return False
    try:
        req = urllib.request.Request(f'{base}/health', method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            return getattr(resp, 'status', 200) == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def analyser_et_classer_journee(
    matchs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    matchs : dicts avec clés c1,cn,c2, over?, under?, ligne?, o25?, u25?, nom_dom, nom_ext, ref?
    Retourne la liste des payloads analysés + classés (niveaux posés).
    """
    try:
        # Même validation des champs, que le calcul soit local ou distant.
        body = AnalyserRequest(matchs=matchs)
    except ValidationError as e:
        raise AnalyseInvalide(f'Entrées moteur invalides : {e}') from e
    base = _moteur_url()
    if base:
        return _via_http(base, [m.model_dump(exclude_none=True) for m in body.matchs])
    try:
        return post_analyser(body).model_dump(mode='json')['analyses']
    except HTTPException as e:
        raise AnalyseInvalide(str(e.detail)) from e


def _via_http(base: str, matchs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    body = json.dumps({'matchs': matchs}).encode('utf-8')
    req = urllib.request.Request(
        f'{base}/v1/analyser',
        data=body,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        raise AnalyseInvalide(f'Moteur HTTP {e.code}: {detail}') from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AnalyseInvalide(f'Moteur injoignable ({base}) : {e}') from e
    except (ValueError, UnicodeError) as e:
        raise AnalyseInvalide('Réponse moteur illisible.') from e
    if not isinstance(data, dict) or data.get('version_moteur') != VERSION_MOTEUR:
        raise AnalyseInvalide('Version moteur incompatible : mettre à jour le service et la web app ensemble.')
    analyses = data.get('analyses')
    if not isinstance(analyses, list) or not analyses:
        raise AnalyseInvalide('Le moteur ne retourne aucune analyse valide.')
    if any(not isinstance(a, dict) or a.get('version_moteur') != VERSION_MOTEUR for a in analyses):
        raise AnalyseInvalide('Version incohérente dans les analyses retournées.')
    return analyses
