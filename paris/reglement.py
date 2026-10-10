import logging

from django.utils import timezone

from paris.evaluation import evaluer
from paris.gamification import regler_pronostics_match

logger = logging.getLogger(__name__)


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
    inconnus = []
    for opt in options:
        try:
            verdict = evaluer(
                opt.code,
                match.buts_dom,
                match.buts_ext,
                match.buts_dom_mt,
                match.buts_ext_mt,
            )
        except (ValueError, TypeError):
            # Un code que l'app ne connaît pas encore — le moteur en ajoute
            # au fil des marchés. Jusqu'ici l'exception remontait jusqu'à
            # `importer_snapshot`, dans une transaction atomique : TOUT
            # l'import était annulé, scores et statuts des autres matchs
            # compris, et l'exception était avalée en log. L'app servait
            # alors l'ancien instantané indéfiniment, sans aucun signe.
            inconnus.append(opt.code)
            continue
        if verdict is None:
            continue
        opt.resultat = 'gagne' if verdict else 'perdu'
        opt.regle_le = maintenant
        opt.save(update_fields=['resultat', 'regle_le'])
        n += 1
    if inconnus:
        logger.warning(
            'Codes inconnus de l\'évaluateur sur %s : %s — options laissées '
            'en attente, le reste de l\'import est préservé.',
            match, ', '.join(sorted(set(inconnus))),
        )
    regler_pronostics_match(match)
    return n
