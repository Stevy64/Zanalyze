"""Compatibilité historique : tous les calculs proviennent de Zanalyze Engine.

Aucun algorithme ne doit être ajouté ici. Le couple historique `cotes_ou25`
porte implicitement la ligne 2.5 ; les nouvelles entrées utilisent `totaux`.
"""
from engine.moteur import *  # noqa: F401,F403 — API historique
from engine.moteur import analyser as _analyser, choisir_options


def analyser(cotes_1x2, cotes_ou25=None, nom_dom='Domicile', nom_ext='Extérieur',
             *, totaux=None, **kwargs):
    if cotes_ou25 is not None and totaux is not None:
        raise AnalyseInvalide('Fournir cotes_ou25 ou totaux, jamais les deux.')
    if cotes_ou25 is not None:
        if len(cotes_ou25) != 2:
            raise AnalyseInvalide('cotes_ou25 attend deux prix sur la ligne 2.5.')
        totaux = (*cotes_ou25, 2.5)
    return _analyser(cotes_1x2, totaux, nom_dom, nom_ext, **kwargs)


# Ancien nom public ; la sélection est désormais celle du moteur partagé.
choisir_trois = choisir_options
