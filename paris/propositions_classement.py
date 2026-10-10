"""Classement communautaire sur des scénarios vérifiables avant match."""
from collections import defaultdict
from datetime import timedelta
from math import sqrt

from django.utils import timezone

from paris.models import PropositionParis


MIN_MATCHS = 5
FENETRE_JOURS = 90


def resultat_proposition(prop):
    match = prop.match
    if prop.created_at >= match.coup_denvoi or match.statut != 'termine':
        return None
    if match.buts_dom is None or match.buts_ext is None:
        return None
    total = match.buts_dom + match.buts_ext
    issues = {
        'Vainqueur domicile': match.buts_dom > match.buts_ext,
        'Match nul': match.buts_dom == match.buts_ext,
        'Vainqueur extérieur': match.buts_dom < match.buts_ext,
        'Plus de 2,5 buts': total >= 3,
        'Moins de 2,5 buts': total < 3,
    }
    return issues.get(prop.libelle)


def _score_prudent(ok, n):
    """Borne basse de Wilson : une seule réussite ne suffit pas à dominer."""
    if not n:
        return 0
    z = 1.96
    p = ok / n
    z2 = z * z
    return (p + z2 / (2 * n) - z * sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n)


def classement_propositions(user=None):
    cutoff = timezone.now() - timedelta(days=FENETRE_JOURS)
    stats = defaultdict(lambda: {'total': 0, 'valides': 0, 'username': ''})
    qs = (PropositionParis.objects
          .filter(match__coup_denvoi__gte=cutoff, match__statut='termine',
                  match__buts_dom__isnull=False, match__buts_ext__isnull=False)
          .select_related('match', 'auteur')
          .order_by('pk'))
    for prop in qs.iterator(chunk_size=1000):
        resultat = resultat_proposition(prop)
        if resultat is None:
            continue
        row = stats[prop.auteur_id]
        row['username'] = prop.auteur.username
        row['total'] += 1
        row['valides'] += int(resultat)
    rows = []
    for user_id, st in stats.items():
        n, ok = st['total'], st['valides']
        rows.append({
            'user_id': user_id, 'username': st['username'],
            'total': n, 'valides': ok,
            'taux': round(100 * ok / n),
            'score': round(100 * _score_prudent(ok, n)),
            'eligible': n >= MIN_MATCHS,
            'restants': max(0, MIN_MATCHS - n),
        })
    rows.sort(key=lambda row: (
        -int(row['eligible']), -row['score'] if row['eligible'] else -row['total'],
        -row['total'] if row['eligible'] else -row['valides'],
        row['username'].casefold(),
    ))
    rang = 0
    for row in rows:
        if row['eligible']:
            rang += 1
            row['rang'] = rang
        else:
            row['rang'] = None
    moi = next((row for row in rows if user and row['user_id'] == user.id), None)
    if user and moi is None:
        moi = {'user_id': user.id, 'username': user.username, 'total': 0,
               'valides': 0, 'taux': 0, 'score': 0, 'eligible': False,
               'restants': MIN_MATCHS, 'rang': None}
    return {'results': [row for row in rows if row['eligible']][:40],
            'moi': moi, 'minimum': MIN_MATCHS, 'fenetre_jours': FENETRE_JOURS}
