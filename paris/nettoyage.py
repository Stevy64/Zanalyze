"""Nettoyage des doublons d'équipes / matchs laissés par la migration V4.

Cause typique : l'import créait `alaves` à côté de `deportivo-alaves`, donc
deux lignes Match pour la même affiche. Les séquelles d'identité
(Rome – Le Mans) sont aussi retirées quand la vraie rencontre existe.
"""
from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.db.models import Q

from paris.identite import cle_equipe
from paris.models import Equipe, Match


def _cle_club(eq: Equipe) -> str:
    """Clé canonique : nom d'abord, sinon slug (ex. deportivo-alaves)."""
    return cle_equipe(eq.nom) or cle_equipe(eq.slug.replace('-', ' '))


def _garder_equipe(a: Equipe, b: Equipe) -> Equipe:
    """Préfère le slug canonique / le plus court / le plus récent."""
    ca = _cle_club(a)
    if a.slug == ca and b.slug != ca:
        return a
    if b.slug == ca and a.slug != ca:
        return b
    if len(a.slug) != len(b.slug):
        return a if len(a.slug) < len(b.slug) else b
    return a if a.pk >= b.pk else b


def _garder_match(a: Match, b: Match) -> Match:
    """Préfère la ligne avec sofascore_id ESPN, sinon celle qui a une analyse."""
    def score(m: Match) -> tuple:
        sid = m.sofascore_id or 0
        espn = 1 if sid >= 100_000_000 else (0 if sid else -1)
        has_ana = 0
        try:
            _ = m.analyse
            has_ana = 1
        except Exception:
            has_ana = 0
        return (espn, has_ana, sid, m.pk)

    return a if score(a) >= score(b) else b


def _fusionner_matchs(garder: Match, jeter: Match) -> None:
    if garder.pk == jeter.pk:
        return
    Match.objects.filter(pk=jeter.pk).update(sofascore_id=None)
    jeter.delete()


@transaction.atomic
def nettoyer_doublons() -> dict[str, int]:
    """Fusionne les équipes synonymes et les matchs en double. Retourne des compteurs."""
    stats = {
        'equipes_fusionnees': 0,
        'matchs_doublons': 0,
        'matchs_absurdes': 0,
    }

    # 1) Doublons d'affiche : même compétition, même coup d'envoi, mêmes clubs.
    par_fenetre: dict[tuple, list[Match]] = defaultdict(list)
    qs = Match.objects.select_related('domicile', 'exterieur', 'competition').all()
    for m in qs:
        cle = (m.competition_id, m.coup_denvoi.isoformat())
        par_fenetre[cle].append(m)

    for groupe in par_fenetre.values():
        if len(groupe) < 2:
            continue
        buckets: dict[tuple[str, str], list[Match]] = defaultdict(list)
        for m in groupe:
            kd = _cle_club(m.domicile)
            ke = _cle_club(m.exterieur)
            buckets[(kd, ke)].append(m)
        for lot in buckets.values():
            if len(lot) < 2:
                continue
            garder = lot[0]
            for autre in lot[1:]:
                garder = _garder_match(garder, autre)
            for m in lot:
                if m.pk != garder.pk:
                    _fusionner_matchs(garder, m)
                    stats['matchs_doublons'] += 1

    # 2) Affiches absurdes : Rome – Le Mans alors que Rome – Inter existe.
    for m in list(Match.objects.select_related('domicile', 'exterieur', 'competition')):
        if _cle_club(m.exterieur) != 'le-mans' and 'le-mans' not in (m.exterieur.slug or ''):
            continue
        if m.competition.code not in ('SA', 'UCL', 'UEL', 'CI'):
            continue
        jumeau = Match.objects.filter(
            competition=m.competition,
            coup_denvoi=m.coup_denvoi,
            domicile=m.domicile,
        ).exclude(pk=m.pk).select_related('exterieur')
        for j in jumeau:
            if _cle_club(j.exterieur) == 'inter' or 'inter' in j.exterieur.slug:
                _fusionner_matchs(j, m)
                stats['matchs_absurdes'] += 1
                break

    # 3) Fusion d'équipes à **même clé canonique** uniquement (pas d'inclusion
    # floue : Paris FC ≠ PSG).
    equipes = list(Equipe.objects.all())
    par_cle: dict[str, list[Equipe]] = defaultdict(list)
    for e in equipes:
        par_cle[_cle_club(e)].append(e)

    for cle, syn in par_cle.items():
        if not cle or len(syn) < 2:
            continue
        garder = syn[0]
        for autre in syn[1:]:
            garder = _garder_equipe(garder, autre)
        for e in syn:
            if e.pk == garder.pk:
                continue
            matchs = list(Match.objects.filter(Q(domicile=e) | Q(exterieur=e)))
            for m in matchs:
                new_dom = garder if m.domicile_id == e.pk else m.domicile
                new_ext = garder if m.exterieur_id == e.pk else m.exterieur
                if new_dom.pk == new_ext.pk:
                    m.delete()
                    stats['matchs_doublons'] += 1
                    continue
                conflit = Match.objects.filter(
                    domicile=new_dom,
                    exterieur=new_ext,
                    coup_denvoi=m.coup_denvoi,
                ).exclude(pk=m.pk).first()
                if conflit:
                    _fusionner_matchs(_garder_match(conflit, m), m)
                    stats['matchs_doublons'] += 1
                else:
                    Match.objects.filter(pk=m.pk).update(
                        domicile=new_dom, exterieur=new_ext,
                    )
            restants = Match.objects.filter(Q(domicile=e) | Q(exterieur=e)).count()
            if restants:
                # Ne jamais casser sur PROTECT : on laisse l'équipe orpheline.
                continue
            e.delete()
            stats['equipes_fusionnees'] += 1

    return stats
