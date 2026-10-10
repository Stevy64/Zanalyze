"""Justifications de tips — courtes, factuelles, lisibles."""
from __future__ import annotations

from typing import Any


def _pct(p: float | None) -> str:
    if p is None:
        return '—'
    return f'{round(float(p) * 100)} %'


def _txt(val: Any) -> str:
    return (str(val) if val is not None else '').strip()


def _court(s: str, n: int = 140) -> str:
    s = ' '.join(_txt(s).split())
    if len(s) <= n:
        return s
    coupe = s[: n - 1].rsplit(' ', 1)[0]
    return (coupe or s[: n - 1]).rstrip('.,;:') + '…'


def _phrase(s: str) -> str:
    s = _txt(s)
    if not s:
        return ''
    return s if s.endswith(('.', '!', '?', '…')) else s + '.'


def _niv_label(niveau: str) -> str:
    return {
        'prudente': 'Prudent',
        'recommandee': 'Recommandé',
        'filet': 'Sécurité',
        'equilibree': 'Équilibrée',
        'audacieuse': 'Audacieuse',
    }.get(niveau, niveau or 'Tip')


def _arg(cle: str, titre: str, texte: str, icon: str) -> dict[str, str] | None:
    texte = _phrase(_court(texte, 160))
    if not texte:
        return None
    return {'cle': cle, 'titre': titre, 'texte': texte, 'icon': icon}


def _accroche(
    *,
    libelle: str,
    niveau: str,
    p: float | None,
    domicile: str,
    exterieur: str,
    contexte: Any | None,
) -> str:
    duo = f'{domicile} – {exterieur}'.strip(' –')
    conf = _pct(p)
    if niveau == 'filet':
        base = f'Sécurité · « {libelle} » ({conf})'
        if duo:
            base += f' sur {duo}'
        return base + ' — repli si le tip principal rate.'
    base = f'« {libelle} » · {conf}'
    if duo:
        base += f' · {duo}'
    has_faits = bool(contexte) and any(
        _txt(getattr(contexte, f, ''))
        for f in ('forme_dom', 'forme_ext', 'confrontations', 'absents_dom', 'absents_ext', 'a_savoir')
    )
    return base + (' · faits terrain.' if has_faits else ' · lecture cotes.')


def _pourquoi(
    *,
    libelle: str,
    famille: str,
    niveau: str,
    contexte: Any | None,
    analyse: Any | None,
    explication: str = '',
) -> str:
    """Le « pourquoi » du moteur, ou rien d'inventé.

    Cette fonction choisissait auparavant une phrase par mots-clés dans le
    libellé, et la servait aux comptes Premium sous le titre « Pourquoi ce
    tip ». Deux de ces phrases affirmaient quelque chose que rien n'avait
    vérifié : « Marché + modèle alignés sur … » prétendait un accord entre
    cote et calcul, et « Historique du duel cohérent avec ce scénario »
    une cohérence que l'app ne mesure pas. Pendant ce temps, le champ
    `explication` du moteur était jeté à l'import.

    Désormais : l'explication du moteur d'abord ; à défaut, une phrase
    strictement factuelle tirée du contexte que le moteur a lui-même fourni
    ou de son score modal ; et si l'on n'a rien, on le dit.
    """
    explication = _txt(explication)
    if explication:
        return _phrase(explication)

    tendance = _txt(getattr(contexte, 'tendance_buts', None) if contexte else '')
    h2h = _txt(getattr(contexte, 'confrontations', None) if contexte else '')
    lib = (libelle or '').lower()
    fam = (famille or '').lower()

    # Repli : uniquement du factuel, repris du contexte publié par le moteur.
    if ('but' in lib or 'total' in fam) and tendance:
        return tendance
    score = _txt(getattr(analyse, 'score_probable', '')) if analyse else ''
    if score:
        return f'Score le plus probable estimé à {score}.'
    if h2h:
        return h2h
    return 'Le moteur n’a pas publié d’explication pour ce tip.'


def _lecture_cotes(analyse: Any | None, domicile: str, exterieur: str) -> str:
    if analyse is None:
        return ''
    try:
        p1 = float(getattr(analyse, 'p1', 0) or 0)
        pn = float(getattr(analyse, 'pn', 0) or 0)
        p2 = float(getattr(analyse, 'p2', 0) or 0)
    except (TypeError, ValueError):
        return ''
    if p1 + pn + p2 <= 0:
        return ''
    score = _txt(getattr(analyse, 'score_probable', ''))
    s = (
        f'{domicile or "Dom"} {_pct(p1)} · Nul {_pct(pn)} · '
        f'{exterieur or "Ext"} {_pct(p2)}'
    )
    if score:
        s += f' · score {score}'
    return s


def justifier_option(
    *,
    option: Any,
    analyse: Any | None = None,
    contexte: Any | None = None,
    domicile: str = '',
    exterieur: str = '',
) -> dict[str, Any]:
    """Titre, accroche courte et 2–3 arguments max."""
    libelle = getattr(option, 'libelle', None) or (
        option.get('libelle') if isinstance(option, dict) else ''
    )
    niveau = getattr(option, 'niveau', None) or (
        option.get('niveau') if isinstance(option, dict) else ''
    )
    famille = getattr(option, 'famille', None) or (
        option.get('famille') if isinstance(option, dict) else ''
    )
    p = (
        getattr(option, 'probabilite', None)
        if not isinstance(option, dict)
        else option.get('probabilite')
    )
    # Le « pourquoi » vient du moteur. L'app ne le fabrique plus.
    explication = (
        getattr(option, 'explication', None)
        if not isinstance(option, dict)
        else option.get('explication')
    ) or ''

    titre = f'{_niv_label(niveau or "")} · {libelle}'
    accroche = _accroche(
        libelle=libelle or 'ce tip',
        niveau=niveau or '',
        p=p,
        domicile=domicile,
        exterieur=exterieur,
        contexte=contexte,
    )

    arguments: list[dict[str, str]] = []

    def push(item: dict[str, str] | None) -> None:
        if item and len(arguments) < 3:
            if any(a['texte'] == item['texte'] for a in arguments):
                return
            arguments.append(item)

    if contexte is not None:
        forme_d = _txt(getattr(contexte, 'forme_dom', ''))
        forme_e = _txt(getattr(contexte, 'forme_ext', ''))
        if forme_d or forme_e:
            if forme_d and forme_e:
                push(_arg(
                    'forme',
                    'Forme',
                    f'{_court(forme_d, 70)} · {_court(forme_e, 70)}',
                    'activity',
                ))
            else:
                push(_arg('forme', 'Forme', forme_d or forme_e, 'activity'))

        push(_arg(
            'h2h',
            'Confrontations',
            getattr(contexte, 'confrontations', ''),
            'swords',
        ))

        abs_d = _txt(getattr(contexte, 'absents_dom', ''))
        abs_e = _txt(getattr(contexte, 'absents_ext', ''))
        if abs_d or abs_e:
            bits = []
            if abs_d:
                bits.append(f'{domicile or "Dom"} : {_court(abs_d, 50)}')
            if abs_e:
                bits.append(f'{exterieur or "Ext"} : {_court(abs_e, 50)}')
            push(_arg('absents', 'Absents', ' · '.join(bits), 'user-x'))

        if len(arguments) < 3:
            push(_arg(
                'savoir',
                'Conditions',
                getattr(contexte, 'a_savoir', ''),
                'cloud',
            ))

    push(_arg(
        'lecture',
        'Pourquoi ce tip',
        _pourquoi(
            libelle=libelle or '',
            famille=famille or '',
            niveau=niveau or '',
            contexte=contexte,
            analyse=analyse,
            explication=explication,
        ),
        'crosshair',
    ))

    if len(arguments) < 3:
        push(_arg(
            'cotes',
            'Cotes',
            _lecture_cotes(analyse, domicile, exterieur),
            'info',
        ))

    if niveau == 'filet' and len(arguments) < 3:
        push(_arg(
            'filet',
            'Rôle',
            'Complément de sécurité, pas un tip audacieux.',
            'shield',
        ))

    if not arguments:
        push(_arg(
            'fallback',
            'Données',
            'Peu de contexte terrain : tip basé surtout sur les cotes.',
            'info',
        ))

    return {
        'titre': titre,
        'accroche': accroche,
        'arguments': arguments[:3],
        'points': [a['texte'] for a in arguments[:3]],
        'niveau': niveau,
        'probabilite': p,
        'libelle': libelle,
    }
