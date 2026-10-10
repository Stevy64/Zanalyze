"""Snapshot matchs + cotes + analyses pour déploiement hors sync live (ex. PythonAnywhere)."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from paris.models import Analyse, Competition, Contexte, Cote, Equipe, Match, Option
from paris.moteur import VERSION_MOTEUR
from paris.reglement import regler_match
from paris.identite import cle_equipe

SNAPSHOT_VERSION = 1


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _dec(v) -> float | None:
    if v is None:
        return None
    return float(v)


def exporter_snapshot(*, jours: int | None = None, enrichir_clubs: bool = False) -> dict[str, Any]:
    """Exporte les matchs « réels » (avec sofascore_id) + dépendances."""
    qs = (
        Match.objects
        .filter(sofascore_id__isnull=False)
        .select_related('competition', 'domicile', 'exterieur', 'analyse', 'contexte')
        .prefetch_related('cotes', 'analyse__options')
        .order_by('coup_denvoi')
    )
    if jours is not None and jours > 0:
        from datetime import timedelta
        from django.utils import timezone
        debut = timezone.now() - timedelta(days=jours)
        fin = timezone.now() + timedelta(days=jours)
        qs = qs.filter(coup_denvoi__gte=debut, coup_denvoi__lte=fin)

    matchs = list(qs)
    comp_ids = {m.competition_id for m in matchs}
    eq_ids = {m.domicile_id for m in matchs} | {m.exterieur_id for m in matchs}

    competitions = [
        {
            'code': c.code,
            'nom': c.nom,
            'pays': c.pays,
            'ordre': c.ordre,
            'actif': c.actif,
            'sofascore_id': c.sofascore_id,
        }
        for c in Competition.objects.filter(pk__in=comp_ids).order_by('ordre', 'code')
    ]
    equipes = []
    from paris.clubs import enrichir_equipe_pour_snapshot
    for e in Equipe.objects.filter(pk__in=eq_ids).order_by('slug'):
        equipes.append(enrichir_equipe_pour_snapshot(e, resoudre_externe=enrichir_clubs))

    out_matchs = []
    for m in matchs:
        bloc: dict[str, Any] = {
            'sofascore_id': m.sofascore_id,
            'competition_code': m.competition.code,
            'domicile_slug': m.domicile.slug,
            'exterieur_slug': m.exterieur.slug,
            'coup_denvoi': _iso(m.coup_denvoi),
            'journee': m.journee,
            'statut': m.statut,
            'buts_dom': m.buts_dom,
            'buts_ext': m.buts_ext,
            'buts_dom_mt': m.buts_dom_mt,
            'buts_ext_mt': m.buts_ext_mt,
            'cotes': [
                {
                    'bookmaker': c.bookmaker,
                    'marche': c.marche,
                    'selection': c.selection,
                    'valeur': _dec(c.valeur),
                    'nb_sources': c.nb_sources,
                    'releve_le': _iso(c.releve_le),
                }
                for c in m.cotes.all()
            ],
            'contexte': None,
            'analyse': None,
        }
        try:
            ctx = m.contexte
            bloc['contexte'] = {
                'forme_dom': ctx.forme_dom,
                'forme_ext': ctx.forme_ext,
                'absents_dom': ctx.absents_dom,
                'absents_ext': ctx.absents_ext,
                'tendance_buts': ctx.tendance_buts,
                'a_savoir': ctx.a_savoir,
                'confrontations': ctx.confrontations,
                'fiabilite': ctx.fiabilite,
            }
        except Contexte.DoesNotExist:
            pass
        try:
            a = m.analyse
            bloc['analyse'] = {
                'buts_dom_attendus': a.buts_dom_attendus,
                'buts_ext_attendus': a.buts_ext_attendus,
                'p1': a.p1,
                'pn': a.pn,
                'p2': a.p2,
                'score_probable': a.score_probable,
                'profil': a.profil,
                'marge_marche': a.marge_marche,
                'residu': a.residu,
                'version_moteur': a.version_moteur,
                'options': [
                    {
                        'famille': o.famille,
                        'code': o.code,
                        'libelle': o.libelle,
                        'probabilite': o.probabilite,
                        'cote_juste': o.cote_juste,
                        'niveau': o.niveau,
                        'origine': o.origine,
                        'resultat': o.resultat,
                    }
                    for o in a.options.all()
                ],
            }
        except Analyse.DoesNotExist:
            pass
        out_matchs.append(bloc)

    return {
        'version': SNAPSHOT_VERSION,
        'exporte_le': datetime.now(dt_timezone.utc).isoformat(),
        'competitions': competitions,
        'equipes': equipes,
        'matchs': out_matchs,
    }


def _liberer_equipe_uniques(
    *,
    slug: str,
    nom: str,
    sid: int | None,
    thesportsdb_id: int | None,
    except_pk: int | None,
) -> None:
    """Renomme / libère slug, nom, sofascore_id déjà pris par une autre équipe."""
    autres = Equipe.objects.all()
    if except_pk:
        autres = autres.exclude(pk=except_pk)

    other = autres.filter(slug=slug).first()
    if other:
        other.slug = f'{other.slug}-old-{other.pk}'[:50]
        other.save(update_fields=['slug'])

    other = autres.filter(nom=nom).first()
    if other:
        other.nom = f'{other.nom} (ancien {other.pk})'[:80]
        other.save(update_fields=['nom'])

    if sid is not None:
        other = autres.filter(sofascore_id=sid).first()
        if other:
            other.sofascore_id = None
            other.save(update_fields=['sofascore_id'])

    if thesportsdb_id is not None:
        other = autres.filter(thesportsdb_id=thesportsdb_id).first()
        if other:
            other.thesportsdb_id = None
            other.save(update_fields=['thesportsdb_id'])


def _trouver_equipe_connue(nom: str, slug: str) -> Equipe | None:
    """Retrouve une équipe déjà en base même si le slug a changé (V3 → V4)."""
    eq = Equipe.objects.filter(slug=slug).first()
    if eq:
        return eq
    eq = Equipe.objects.filter(nom=nom).first()
    if eq:
        return eq
    cible = cle_equipe(nom) or cle_equipe(slug.replace('-', ' '))
    if not cible:
        return None
    # Uniquement même clé canonique (alias) — pas d'inclusion floue Paris ⊂ PSG.
    for cand in Equipe.objects.all().only('id', 'nom', 'slug', 'nom_court'):
        if cle_equipe(cand.nom) == cible:
            return cand
        if cle_equipe(cand.slug.replace('-', ' ')) == cible:
            return cand
    return None


def _upsert_equipe(e: dict[str, Any]) -> Equipe:
    """
    Upsert robuste : sid, slug, nom, puis identité canonique (meme_club).
    Évite les doublons alaves / deportivo-alaves après migration V4.
    """
    sid = e.get('sofascore_id')
    nom = e['nom']
    slug = e['slug']
    tsdb = e.get('thesportsdb_id')
    defaults = {
        'nom': nom,
        'nom_court': e.get('nom_court') or nom[:24],
        'slug': slug,
        'thesportsdb_id': tsdb,
        'logo_externe': e.get('logo_externe') or '',
        'fiche_club': e.get('fiche_club') or {},
    }

    eq = None
    if sid:
        eq = Equipe.objects.filter(sofascore_id=sid).first()
    if eq is None:
        eq = _trouver_equipe_connue(nom, slug)

    if eq is None:
        _liberer_equipe_uniques(
            slug=slug, nom=nom, sid=sid, thesportsdb_id=tsdb, except_pk=None,
        )
        return Equipe.objects.create(sofascore_id=sid, **defaults)

    _liberer_equipe_uniques(
        slug=slug, nom=nom, sid=sid, thesportsdb_id=tsdb, except_pk=eq.pk,
    )
    for k, v in defaults.items():
        setattr(eq, k, v)
    # Toujours aligner sur le snapshot : un null V4 efface un id ESPN
    # indûment stocké comme sofascore_id (cause du bug d'identité).
    eq.sofascore_id = sid
    eq.save()
    return eq


def _a_un_resultat(match: Match) -> bool:
    return match.buts_dom is not None and match.buts_ext is not None


def _remplacer_options(analyse: Analyse, options: list[dict[str, Any]]) -> int:
    """Aligne les options sur celles du moteur, sans rien détruire d'utile.

    L'import faisait `analyse.options.all().delete()` avant de recréer. Or
    `VoteOption.option` est en CASCADE : chaque import effaçait donc **tous
    les votes de consensus** des utilisateurs, toutes les deux heures. La
    fonctionnalité « comparer le consensus à la prédiction » ne pouvait pas
    fonctionner.

    On met donc à jour par code, comme le fait déjà `calculer_analyses`, et
    on ne supprime que les options encore en attente que le moteur ne publie
    plus. Un règlement déjà acquis n'est jamais réécrit : il appartient au
    bilan.
    """
    n = 0
    vus: set[str] = set()
    existantes = {o.code: o for o in analyse.options.all()}
    for o in options:
        code = o.get('code')
        if not code:
            continue
        vus.add(code)
        champs = {
            'famille': o.get('famille') or '',
            'libelle': o.get('libelle') or '',
            'probabilite': o['probabilite'],
            'cote_juste': o['cote_juste'],
            'niveau': o.get('niveau') or 'detail',
            'origine': o.get('origine') or 'calcul',
            # Publiés par le moteur, et jusqu'ici jetés.
            'explication': (o.get('explication') or '')[:300],
            'confiance': o.get('confiance'),
            'probabilite_brute': o.get('p_brute'),
            'calibree': bool(o.get('calibree')),
        }
        ancienne = existantes.get(code)
        if ancienne is None:
            Option.objects.create(analyse=analyse, code=code,
                                  resultat=o.get('resultat') or 'attente',
                                  **champs)
            n += 1
            continue
        for k, v in champs.items():
            setattr(ancienne, k, v)
        # Un résultat acquis ne se réécrit pas depuis un instantané.
        if ancienne.resultat == 'attente':
            ancienne.resultat = o.get('resultat') or 'attente'
        ancienne.save(update_fields=[*champs, 'resultat'])
        n += 1
    # Ce que le moteur ne propose plus, et qui n'a pas encore été réglé.
    analyse.options.filter(resultat='attente').exclude(code__in=vus).delete()
    return n


@transaction.atomic
def importer_snapshot(data: dict[str, Any]) -> dict[str, int]:
    """Upsert snapshot (compétitions, équipes, matchs, cotes, analyses)."""
    if not isinstance(data, dict) or 'matchs' not in data:
        raise ValueError('Snapshot invalide : clé "matchs" manquante.')

    stats = {
        'competitions': 0,
        'equipes': 0,
        'matchs': 0,
        'cotes': 0,
        'analyses': 0,
        'options': 0,
        'contextes': 0,
        'analyses_perimees': 0,
        'votes_preserves': 0,
    }

    # Quand le moteur a calculé, pas quand on l'a importé. `calcule_le` était
    # en `auto_now` : une analyse de trois jours paraissait fraîche de deux
    # heures sur un champ dont le nom promet la date de calcul.
    calcule_le = parse_datetime(data.get('exporte_le') or '') or timezone.now()

    for c in data.get('competitions') or []:
        sid = c.get('sofascore_id')
        if sid:
            # Libère l’id s’il était sur une autre compétition (SofaScore → ESPN).
            Competition.objects.filter(sofascore_id=sid).exclude(code=c['code']).update(
                sofascore_id=None,
            )
        Competition.objects.update_or_create(
            code=c['code'],
            defaults={
                'nom': c.get('nom') or c['code'],
                'pays': c.get('pays') or '',
                'ordre': c.get('ordre', 100),
                'actif': c.get('actif', True),
                'sofascore_id': sid,
            },
        )
        stats['competitions'] += 1

    equipes_par_slug: dict[str, Equipe] = {}
    for e in data.get('equipes') or []:
        eq = _upsert_equipe(e)
        stats['equipes'] += 1
        if e.get('slug'):
            equipes_par_slug[e['slug']] = eq
        equipes_par_slug[eq.slug] = eq

    for m in data.get('matchs') or []:
        sid = m.get('sofascore_id')
        if not sid:
            continue
        competition = Competition.objects.get(code=m['competition_code'])
        domicile = equipes_par_slug.get(m['domicile_slug'])
        exterieur = equipes_par_slug.get(m['exterieur_slug'])
        if domicile is None or exterieur is None:
            continue
        coup = parse_datetime(m['coup_denvoi'])
        if coup is None:
            continue

        match = _upsert_match(
            sid=sid,
            competition=competition,
            domicile=domicile,
            exterieur=exterieur,
            coup=coup,
            journee=m.get('journee') or '',
            statut=m.get('statut') or 'a_venir',
            buts_dom=m.get('buts_dom'),
            buts_ext=m.get('buts_ext'),
            buts_dom_mt=m.get('buts_dom_mt'),
            buts_ext_mt=m.get('buts_ext_mt'),
            ligne_totaux=m.get('ligne_totaux'),
            cle_moteur=m.get('cle_moteur') or f'snapshot:{sid}',
        )
        stats['matchs'] += 1

        # Remplace les cotes exportées (évite les doublons).
        # Une liste VIDE n'est pas une mise à jour : le moteur dit seulement
        # qu'il n'a pas de cote pour ce match. Effacer les anciennes tout en
        # conservant l'analyse laissait 66 matchs sur 396 avec des tips
        # affichés comme courants et plus aucune cote derrière.
        if m.get('cotes'):
            match.cotes.all().delete()
            for c in m['cotes']:
                releve = parse_datetime(c.get('releve_le') or '') or coup
                Cote.objects.create(
                    match=match,
                    bookmaker=c.get('bookmaker') or 'snapshot',
                    marche=c['marche'],
                    selection=c['selection'],
                    valeur=Decimal(str(c['valeur'])),
                    nb_sources=c.get('nb_sources') or 1,
                    releve_le=releve,
                )
                stats['cotes'] += 1

        ctx = m.get('contexte')
        if ctx:
            Contexte.objects.update_or_create(
                match=match,
                defaults={
                    'forme_dom': ctx.get('forme_dom') or '',
                    'forme_ext': ctx.get('forme_ext') or '',
                    'absents_dom': ctx.get('absents_dom') or '',
                    'absents_ext': ctx.get('absents_ext') or '',
                    'tendance_buts': ctx.get('tendance_buts') or '',
                    'a_savoir': ctx.get('a_savoir') or '',
                    'confrontations': ctx.get('confrontations') or '',
                    'fiabilite': ctx.get('fiabilite') or 'moyenne',
                    'source': '',
                },
            )
            stats['contextes'] += 1

        ana = m.get('analyse')
        if ana:
            analyse, _ = Analyse.objects.update_or_create(
                match=match,
                defaults={
                    'buts_dom_attendus': ana['buts_dom_attendus'],
                    'buts_ext_attendus': ana['buts_ext_attendus'],
                    'p1': ana['p1'],
                    'pn': ana['pn'],
                    'p2': ana['p2'],
                    'score_probable': ana.get('score_probable') or '',
                    'profil': ana.get('profil') or 'moyen',
                    'marge_marche': ana.get('marge_marche') or 0,
                    'residu': ana.get('residu') or 0,
                    'version_moteur': ana.get('version_moteur') or VERSION_MOTEUR,
                    # Verdicts du moteur, repris tels quels plutôt que
                    # recalculés avec les seuils de l'app.
                    'douteuse': bool(ana.get('douteuse')),
                    'source_cotes': (ana.get('source_cotes') or '')[:40],
                    'exposition_lot': ana.get('exposition_lot'),
                    'calcule_le': calcule_le,
                },
            )
            stats['analyses'] += 1
            stats['options'] += _remplacer_options(analyse, ana.get('options') or [])
        elif not _a_un_resultat(match):
            # Le moteur ne publie plus d'analyse pour ce match : la précédente
            # n'est plus courante. La garder affichait une analyse orpheline,
            # invérifiable et impossible à rafraîchir. On ne touche pas à celles
            # des matchs déjà joués : leur bilan, lui, est acquis.
            supprimees = Analyse.objects.filter(match=match).delete()[0]
            if supprimees:
                stats['analyses_perimees'] = stats.get('analyses_perimees', 0) + 1

        if match.statut == 'termine':
            regler_match(match)

    from paris.nettoyage import nettoyer_doublons
    stats_nettoyage = nettoyer_doublons()
    stats['doublons_equipes'] = stats_nettoyage.get('equipes_fusionnees', 0)
    stats['doublons_matchs'] = (
        stats_nettoyage.get('matchs_doublons', 0)
        + stats_nettoyage.get('matchs_absurdes', 0)
    )
    return stats


def _upsert_match(
    *,
    sid: int,
    competition: Competition,
    domicile: Equipe,
    exterieur: Equipe,
    coup,
    journee: str,
    statut: str,
    buts_dom,
    buts_ext,
    buts_dom_mt,
    buts_ext_mt,
    ligne_totaux=None,
    cle_moteur='',
) -> Match:
    """
    Upsert match par sofascore_id, sinon par (domicile, exterieur, coup_d'envoi).

    Cas V4 : une ligne ESPN (mauvaises équipes, bug d'identité) et une ligne
    à la bonne identité (autre sid) coexistent. Réécrire la première heurte
    alors la contrainte unique — il faut fusionner avant le save.
    """
    defaults = {
        'competition': competition,
        'domicile': domicile,
        'exterieur': exterieur,
        'coup_denvoi': coup,
        'journee': journee,
        'statut': statut,
        'buts_dom': buts_dom,
        'buts_ext': buts_ext,
        'buts_dom_mt': buts_dom_mt,
        'buts_ext_mt': buts_ext_mt,
        'sofascore_id': sid,
        # Le seuil de buts réellement coté : 35 % des rencontres ne sont pas
        # cotées à 2,5, et l'ignorer faisait lire un prix sur 3,5 comme un
        # prix sur 2,5.
        'ligne_totaux': ligne_totaux,
        'cle_moteur': cle_moteur,
    }

    by_sid = Match.objects.filter(sofascore_id=sid).first()
    by_key = Match.objects.filter(
        domicile=domicile,
        exterieur=exterieur,
        coup_denvoi=coup,
    ).first()

    # Même affiche sous d'anciens slugs (alaves / deportivo-alaves, etc.).
    if by_key is None:
        cible_d = cle_equipe(domicile.nom)
        cible_e = cle_equipe(exterieur.nom)
        for cand in Match.objects.filter(
            competition=competition, coup_denvoi=coup,
        ).select_related('domicile', 'exterieur'):
            if (
                cle_equipe(cand.domicile.nom) == cible_d
                and cle_equipe(cand.exterieur.nom) == cible_e
            ):
                by_key = cand
                break

    if by_sid and by_key and by_sid.pk != by_key.pk:
        # Garder l'affiche correcte ; le doublon sid (souvent corrompu) part.
        Match.objects.filter(pk=by_sid.pk).update(sofascore_id=None)
        by_sid.delete()
        match = by_key
    elif by_sid is not None:
        match = by_sid
    elif by_key is not None:
        match = by_key
    else:
        return Match.objects.create(**defaults)

    Match.objects.filter(sofascore_id=sid).exclude(pk=match.pk).update(
        sofascore_id=None,
    )
    for k, v in defaults.items():
        setattr(match, k, v)
    match.save()
    return match
