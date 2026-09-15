"""Gamification Premium — pronostics 1X2, points et grades."""
from __future__ import annotations

GRADES = (
    (0, 'mougou', 'Mougou'),
    (40, 'zanalyste', 'Zanalyste'),
    (120, 'ndoss', 'Ndoss'),
    (300, 'boss', 'Boss'),
)

POINTS_BONNE_PRED = 12
POINTS_PARTICIPATION = 2


def grade_pour(points: int) -> str:
    code = 'mougou'
    for seuil, cle, _lib in GRADES:
        if points >= seuil:
            code = cle
    return code


def libelle_grade(code: str) -> str:
    for _seuil, cle, lib in GRADES:
        if cle == code:
            return lib
    return 'Mougou'


def choix_gagnant(buts_dom: int, buts_ext: int) -> str:
    if buts_dom > buts_ext:
        return '1'
    if buts_dom < buts_ext:
        return '2'
    return 'N'


def regler_pronostics_match(match) -> int:
    """Attribue les points des pronostics Premium sur un match terminé."""
    if match.statut != 'termine':
        return 0
    if match.buts_dom is None or match.buts_ext is None:
        return 0
    from paris.models import PronosticPremium

    gagnant = choix_gagnant(int(match.buts_dom), int(match.buts_ext))
    n = 0
    qs = PronosticPremium.objects.filter(match=match, points__isnull=True).select_related(
        'user__profil',
    )
    for prono in qs:
        ok = prono.choix == gagnant
        pts = POINTS_BONNE_PRED if ok else POINTS_PARTICIPATION
        prono.points = pts
        prono.gagne = ok
        prono.save(update_fields=['points', 'gagne'])
        profil = getattr(prono.user, 'profil', None)
        if profil is None:
            from paris.models import Profil
            profil, _ = Profil.objects.get_or_create(user=prono.user)
        profil.points_premium = int(profil.points_premium or 0) + pts
        profil.save(update_fields=['points_premium'])
        n += 1
    return n
