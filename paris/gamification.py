"""Gamification membres — pronostics 1X2, propositions, grades et objectifs."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

GRADES = (
    (0, 'mougou', 'Mougou'),
    (40, 'zanalyste', 'Zanalyste'),
    (120, 'ndoss', 'Ndoss'),
    (300, 'boss', 'Boss'),
)

POINTS_BONNE_PRED = 12
POINTS_PARTICIPATION = 2
POINTS_PROPOSITION = 5
POINTS_DECAY_PAR_JOUR = 1
# Bonus série de bons pronostics (appliqué au règlement du N-ième gain d’affilée).
STREAK_BONUS = (
    (3, 5),
    (5, 10),
    (10, 25),
)


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
    return {
        'rookie': 'Mougou',
        'analyste': 'Zanalyste',
        'stratege': 'Ndoss',
        'oracle': 'Boss',
    }.get(code, 'Mougou')


def objectif_suivant(points: int) -> dict:
    """Prochain grade à viser + barre de progression."""
    pts = max(0, int(points or 0))
    courant = grade_pour(pts)
    courant_lib = libelle_grade(courant)
    seuil_courant = 0
    for seuil, cle, _lib in GRADES:
        if cle == courant:
            seuil_courant = seuil
            break
    prochain = None
    for seuil, cle, lib in GRADES:
        if pts < seuil:
            prochain = {'grade': cle, 'libelle': lib, 'seuil': seuil}
            break
    if prochain is None:
        return {
            'grade_actuel': courant,
            'libelle_actuel': courant_lib,
            'points': pts,
            'seuil_actuel': seuil_courant,
            'prochain_grade': 'boss',
            'prochain_libelle': 'Boss',
            'seuil': 300,
            'reste': 0,
            'progress_pct': 100,
            'atteint_max': True,
            'reste_libelle': '',
            'message': (
                'Grade max — Boss. Attention : −1 pt / 24 h sans activité, '
                'continue à parier pour rester au top !'
            ),
        }
    span = max(1, prochain['seuil'] - seuil_courant)
    done = pts - seuil_courant
    pct = min(100, max(0, round(100 * done / span)))
    reste = prochain['seuil'] - pts
    return {
        'grade_actuel': courant,
        'libelle_actuel': courant_lib,
        'points': pts,
        'seuil_actuel': seuil_courant,
        'prochain_grade': prochain['grade'],
        'prochain_libelle': prochain['libelle'],
        'seuil': prochain['seuil'],
        'reste': reste,
        'progress_pct': pct,
        'atteint_max': False,
        'reste_libelle': f'{reste} pts restants pour devenir {prochain["libelle"]}',
        'message': (
            f'Plus que {reste} pts pour devenir {prochain["libelle"]} '
            f'(pose un 1X2 ou propose un pari). −1 pt / 24 h.'
        ),
    }


def choix_gagnant(buts_dom: int, buts_ext: int) -> str:
    if buts_dom > buts_ext:
        return '1'
    if buts_dom < buts_ext:
        return '2'
    return 'N'


def _streak_bonus(serie: int) -> int:
    bonus = 0
    for besoin, pts in STREAK_BONUS:
        if serie >= besoin:
            bonus = pts
    return bonus


def appliquer_decay(profil) -> int:
    """
    Retire 1 pt par période de 24 h écoulée depuis points_decay_le.
    Plancher à 0. Retourne le nombre de points retirés.
    """
    now = timezone.now()
    if profil.points_decay_le is None:
        profil.points_decay_le = now
        profil.save(update_fields=['points_decay_le'])
        return 0
    delta = now - profil.points_decay_le
    jours = int(delta.total_seconds() // 86400)
    if jours < 1:
        return 0
    pts = int(profil.points_premium or 0)
    retire = min(pts, jours * POINTS_DECAY_PAR_JOUR)
    profil.points_premium = pts - retire
    # Avance l’horloge du nombre de jours complets appliqués (pas « now »
    # pour ne pas perdre une fraction de jour déjà écoulée).
    profil.points_decay_le = profil.points_decay_le + timedelta(days=jours)
    if profil.points_decay_le > now:
        profil.points_decay_le = now
    profil.save(update_fields=['points_premium', 'points_decay_le'])
    return retire


def decroitre_tous_les_profils() -> dict[str, int]:
    """Batch pour cron / commande : applique le decay sur tous les profils."""
    from paris.models import Profil

    n_profils = 0
    n_points = 0
    for profil in Profil.objects.filter(points_premium__gt=0).iterator():
        retire = appliquer_decay(profil)
        if retire:
            n_profils += 1
            n_points += retire
        elif profil.points_decay_le is None:
            n_profils += 0
    # Initialise aussi les profils à 0 pts sans horloge
    for profil in Profil.objects.filter(points_decay_le__isnull=True).iterator():
        appliquer_decay(profil)
    return {'profils_touches': n_profils, 'points_retires': n_points}


def stats_utilisateur(user) -> dict:
    from paris.models import PronosticPremium, PropositionParis

    qs = PronosticPremium.objects.filter(user=user)
    regles = qs.filter(points__isnull=False)
    joues = regles.count()
    gagnes = regles.filter(gagne=True).count()
    en_attente = qs.filter(points__isnull=True).count()
    props = PropositionParis.objects.filter(auteur=user).count()

    serie = 0
    for prono in regles.order_by('-match__coup_denvoi', '-id'):
        if prono.gagne:
            serie += 1
        else:
            break

    taux = round(100 * gagnes / joues) if joues else None
    return {
        'pronos_joues': joues,
        'pronos_gagnes': gagnes,
        'pronos_en_attente': en_attente,
        'taux_reussite': taux,
        'serie_actuelle': serie,
        'propositions': props,
    }


def hint_actions(stats: dict, objectif: dict) -> str:
    if stats.get('pronos_joues', 0) == 0 and stats.get('propositions', 0) == 0:
        return (
            'Premier pas : ouvre un match à venir, pose ton 1X2 '
            f'(+{POINTS_PARTICIPATION} à +{POINTS_BONNE_PRED} pts) '
            f'ou propose un pari (+{POINTS_PROPOSITION} pts). '
            f'Attention : −{POINTS_DECAY_PAR_JOUR} pt / 24 h.'
        )
    if not objectif.get('atteint_max'):
        return objectif.get('message') or ''
    return (
        'Tu es Boss — parie régulièrement : −1 pt disparaît chaque 24 h '
        'si tu restes inactif.'
    )


def categorie_classement(user) -> str:
    """Catégorie de classement : membre | premium."""
    from paris.roles import categorie_user
    cat = categorie_user(user)
    if cat == 'premium':
        return 'premium'
    return 'membre'


def progression_utilisateur(user) -> dict:
    from paris.models import Profil

    profil, _ = Profil.objects.get_or_create(user=user)
    try:
        appliquer_decay(profil)
        profil.refresh_from_db()
    except Exception:
        # Ne jamais bloquer login / info si decay ou colonnes absentes.
        pass
    pts = int(profil.points_premium or 0)
    grade = grade_pour(pts)
    obj = objectif_suivant(pts)
    stats = stats_utilisateur(user)
    cat = categorie_classement(user)
    return {
        'points': pts,
        'grade': grade,
        'grade_libelle': libelle_grade(grade),
        'categorie_classement': cat,
        'objectif': obj,
        'stats': stats,
        'hint': hint_actions(stats, obj),
        'decay': {
            'par_jour': POINTS_DECAY_PAR_JOUR,
            'message': f'−{POINTS_DECAY_PAR_JOUR} pt toutes les 24 h (plancher à 0).',
        },
        'gains': {
            'prono_ok': POINTS_BONNE_PRED,
            'prono_ko': POINTS_PARTICIPATION,
            'proposition': POINTS_PROPOSITION,
            'serie': [{'a_partir_de': n, 'bonus': b} for n, b in STREAK_BONUS],
        },
    }


def ajouter_points(user, points: int) -> int:
    from paris.models import Profil

    if points <= 0:
        return 0
    profil, _ = Profil.objects.get_or_create(user=user)
    appliquer_decay(profil)
    profil.refresh_from_db()
    profil.points_premium = int(profil.points_premium or 0) + int(points)
    # Gagner des points ne reset pas le decay : la pression reste.
    if profil.points_decay_le is None:
        profil.points_decay_le = timezone.now()
        profil.save(update_fields=['points_premium', 'points_decay_le'])
    else:
        profil.save(update_fields=['points_premium'])
    return int(points)


def crediter_proposition(user) -> int:
    """+5 pts quand un membre publie une proposition (1 seule / match)."""
    return ajouter_points(user, POINTS_PROPOSITION)


def regler_pronostics_match(match) -> int:
    """Attribue les points des pronostics sur un match terminé (+ bonus série)."""
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
        serie = 0
        if ok:
            anterieurs = (
                PronosticPremium.objects
                .filter(user=prono.user, points__isnull=False)
                .exclude(pk=prono.pk)
                .order_by('-match__coup_denvoi', '-id')
            )
            for prev in anterieurs:
                if prev.gagne:
                    serie += 1
                else:
                    break
            serie += 1
            pts += _streak_bonus(serie)
        prono.points = pts
        prono.gagne = ok
        prono.save(update_fields=['points', 'gagne'])
        ajouter_points(prono.user, pts)
        n += 1
    return n
