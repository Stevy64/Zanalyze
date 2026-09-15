from django.utils import timezone

from paris.evaluation import evaluer
from paris.gamification import regler_pronostics_match


def regler_match(match, maintenant=None):
    """Règle les options en attente d'un match terminé. Retourne le nombre réglé."""
    if match.statut != 'termine':
        return 0
    if match.buts_dom is None or match.buts_ext is None:
        return 0
    if not hasattr(match, 'analyse'):
        regler_pronostics_match(match)
        return 0
    maintenant = maintenant or timezone.now()
    n = 0
    options = match.analyse.options.filter(resultat='attente')
    for opt in options:
        verdict = evaluer(
            opt.code,
            match.buts_dom,
            match.buts_ext,
            match.buts_dom_mt,
            match.buts_ext_mt,
        )
        if verdict is None:
            continue
        opt.resultat = 'gagne' if verdict else 'perdu'
        opt.regle_le = maintenant
        opt.save(update_fields=['resultat', 'regle_le'])
        n += 1
    regler_pronostics_match(match)
    return n
