"""Client TheSportsDB — secours logos / forme / classement (API publique)."""
from __future__ import annotations

import logging
import unicodedata
from datetime import date
from typing import Any
from urllib.parse import quote

try:
    from curl_cffi import requests as _cffi_requests
except ImportError:  # pragma: no cover
    _cffi_requests = None

logger = logging.getLogger(__name__)

# Clé publique gratuite documentée par TheSportsDB (v1).
BASE = 'https://www.thesportsdb.com/api/v1/json/3'

# Compétitions Zanalyze → idLeague TheSportsDB
# Compétitions Zanalyze → idLeague TheSportsDB (ids publics vérifiés)
LIGUES = {
    'PL': 4328,
    'FAC': 4482,
    'EFL': 4570,
    'LIGA': 4335,
    'CDR': 4483,
    'BL': 4331,
    'L1': 4334,
    'SA': 4332,
    'LP': 4344,
    'UCL': 4480,
    'UEL': 4481,
}

_ALIASES = {
    'psg': 'Paris Saint Germain',
    'paris sg': 'Paris Saint Germain',
    'paris saint-germain': 'Paris Saint Germain',
    'olympique de marseille': 'Marseille',
    'olympique lyonnais': 'Lyon',
    'inter milan': 'Inter Milan',
    'inter': 'Inter Milan',
    'fc inter': 'Inter Milan',
    'bayern munich': 'Bayern Munich',
    'fc barcelone': 'Barcelona',
    'barca': 'Barcelona',
    'atletico madrid': 'Atletico Madrid',
    'atlético de madrid': 'Atletico Madrid',
    'manchester united': 'Manchester United',
    'man united': 'Manchester United',
    'man utd': 'Manchester United',
    'manchester city': 'Manchester City',
    'man city': 'Manchester City',
    'tottenham': 'Tottenham',
    'spurs': 'Tottenham',
    'liverpool fc': 'Liverpool',
    'come': 'Como',
}


class SportsDbErreur(RuntimeError):
    pass


def _norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _get(path: str, *, timeout: float = 12) -> dict[str, Any]:
    url = path if path.startswith('http') else f'{BASE}{path}'
    if _cffi_requests is not None:
        r = _cffi_requests.get(url, impersonate='chrome124', timeout=timeout)
        if r.status_code != 200:
            raise SportsDbErreur(f'TheSportsDB {r.status_code} sur {path}')
        if not (r.content or b'').strip():
            return {}
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise SportsDbErreur(f'TheSportsDB JSON invalide sur {path}') from exc
        return data if isinstance(data, dict) else {}

    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 Zanalyze/1.0',
            'Accept': 'application/json',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8').strip()
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as exc:
        raise SportsDbErreur(f'TheSportsDB {exc.code}') from exc
    except urllib.error.URLError as exc:
        raise SportsDbErreur(str(exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise SportsDbErreur(f'TheSportsDB JSON invalide sur {path}') from exc


def saison_str(jour: date | None = None) -> str:
    d = jour or date.today()
    if d.month >= 8:
        return f'{d.year}-{d.year + 1}'
    return f'{d.year - 1}-{d.year}'


def _saisons_a_essayer() -> list[str]:
    """Saison courante puis précédente (tables parfois en retard)."""
    d = date.today()
    courante = saison_str(d)
    if d.month >= 8:
        prec = f'{d.year - 1}-{d.year}'
    else:
        prec = f'{d.year - 2}-{d.year - 1}'
    return [courante, prec]


def chercher_equipe(nom: str) -> dict[str, Any] | None:
    """Retourne le meilleur club Soccer correspondant au nom."""
    q = (nom or '').strip()
    if not q:
        return None
    q_search = _ALIASES.get(_norm(q), q)
    try:
        data = _get(f'/searchteams.php?t={quote(q_search)}')
    except SportsDbErreur:
        return None
    teams = [t for t in (data.get('teams') or []) if (t.get('strSport') or '').lower() == 'soccer']
    if not teams:
        return None
    qn = _norm(q)
    qsn = _norm(q_search)
    meilleurs: list[tuple[int, dict]] = []
    for t in teams:
        name = _norm(t.get('strTeam') or '')
        alt = _norm(t.get('strTeamAlternate') or '')
        short = _norm(t.get('strTeamShort') or '')
        score = 0
        if name in (qn, qsn) or short in (qn, qsn):
            score = 100
        elif qsn in name or qn in name:
            score = 85
        elif name in qsn or name in qn:
            score = 70
        elif qsn in alt or qn in alt:
            score = 60
        else:
            score = 20
        blob = f' {name} {alt} '
        for token in (' u19', ' u21', ' u23', ' women', ' ladies', ' reserve', ' ii', ' b '):
            if token in blob:
                score -= 40
                break
        # Prefer senior clubs from major leagues when tied loosely
        if t.get('strLeague') in (
            'English Premier League', 'Spanish La Liga', 'French Ligue 1',
            'Italian Serie A', 'German Bundesliga', 'Portuguese Primeira Liga',
            'UEFA Champions League',
        ):
            score += 5
        meilleurs.append((score, t))
    meilleurs.sort(key=lambda x: -x[0])
    if not meilleurs or meilleurs[0][0] < 40:
        return None
    return meilleurs[0][1]


def resoudre_id(nom: str, nom_court: str = '') -> int | None:
    t = chercher_equipe(nom) or (chercher_equipe(nom_court) if nom_court else None)
    if not t:
        return None
    try:
        return int(t['idTeam'])
    except (KeyError, TypeError, ValueError):
        return None


def _classement_equipe(team_id: int, league_id: int | None) -> dict[str, Any] | None:
    if not league_id:
        return None
    for season in _saisons_a_essayer():
        try:
            data = _get(f'/lookuptable.php?l={int(league_id)}&s={quote(season)}')
        except SportsDbErreur:
            continue
        for row in data.get('table') or []:
            try:
                if int(row.get('idTeam') or 0) != int(team_id):
                    continue
            except (TypeError, ValueError):
                continue
            return {
                'position': int(row['intRank']) if row.get('intRank') else None,
                'points': int(row['intPoints']) if row.get('intPoints') not in (None, '') else None,
                'joues': int(row['intPlayed']) if row.get('intPlayed') not in (None, '') else None,
                'gagnes': int(row['intWin']) if row.get('intWin') not in (None, '') else None,
                'nuls': int(row['intDraw']) if row.get('intDraw') not in (None, '') else None,
                'perdus': int(row['intLoss']) if row.get('intLoss') not in (None, '') else None,
                'buts_pour': int(row['intGoalsFor']) if row.get('intGoalsFor') not in (None, '') else None,
                'buts_contre': int(row['intGoalsAgainst']) if row.get('intGoalsAgainst') not in (None, '') else None,
                'competition': row.get('strLeague') or row.get('strGroup'),
            }
    return None


def infos_equipe(team_id: int, *, league_code: str | None = None) -> dict[str, Any]:
    """Forme récente, classement éventuel, matchs récents."""
    team_id = int(team_id)
    data = _get(f'/lookupteam.php?id={team_id}')
    teams = data.get('teams') or []
    if not teams:
        raise SportsDbErreur(f'Équipe {team_id} introuvable')
    team = teams[0]

    recents = []
    forme: list[str] = []
    try:
        last = _get(f'/eventslast.php?id={team_id}')
    except SportsDbErreur:
        last = {}
    for ev in (last.get('results') or [])[:8]:
        try:
            hs = int(ev['intHomeScore'])
            aw = int(ev['intAwayScore'])
        except (KeyError, TypeError, ValueError):
            continue
        home = ev.get('strHomeTeam') or ''
        away = ev.get('strAwayTeam') or ''
        is_home = _norm(home) == _norm(team.get('strTeam') or '')
        # fallback id-based if available
        if not is_home and not away:
            continue
        if is_home:
            res = 'W' if hs > aw else ('L' if hs < aw else 'D')
            adversaire = away
        else:
            res = 'W' if aw > hs else ('L' if aw < hs else 'D')
            adversaire = home
        forme.append(res)
        recents.append({
            'adversaire': adversaire,
            'score': f'{hs}-{aw}',
            'domicile': is_home,
            'resultat': res,
            'coup_denvoi': (ev.get('strTimestamp') or ev.get('dateEvent') or None),
        })

    forme_chrono = list(reversed(forme[:5]))
    lid = LIGUES.get((league_code or '').upper()) if league_code else None
    if not lid:
        try:
            lid = int(team.get('idLeague') or 0) or None
        except (TypeError, ValueError):
            lid = None
    classement = _classement_equipe(team_id, lid)

    return {
        'id': team_id,
        'nom': team.get('strTeam'),
        'nom_court': team.get('strTeamShort') or team.get('strTeam'),
        'pays': team.get('strCountry'),
        'forme': forme_chrono,
        'position': (classement or {}).get('position'),
        'note_moyenne': None,
        'classement': classement,
        'recents': recents,
        'badge_url': team.get('strBadge') or team.get('strLogo'),
    }


def logo_bytes(team_id: int) -> tuple[bytes, str]:
    data = _get(f'/lookupteam.php?id={int(team_id)}')
    teams = data.get('teams') or []
    if not teams:
        raise SportsDbErreur('Équipe introuvable')
    url = teams[0].get('strBadge') or teams[0].get('strLogo')
    if not url:
        raise SportsDbErreur('Pas de badge')
    # Prefer tiny for bandwidth when available
    if '/tiny' not in url and url.endswith('.png'):
        tiny = url + '/tiny'
    else:
        tiny = url
    from paris import sofascore as sofa
    try:
        return sofa._http_get_bytes(tiny)
    except Exception:
        return sofa._http_get_bytes(url)
