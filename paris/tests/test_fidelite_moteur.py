"""Le moteur est la seule source : l'app n'invente ni n'altère.

Ces tests verrouillent les défauts constatés le 9 octobre 2026, quand
l'application recalculait les probabilités du moteur, jetait tous ses champs
v4, fabriquait une justification par mots-clés et détruisait les votes des
utilisateurs à chaque import.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from paris.models import Analyse, Competition, Equipe, Match, Option, VoteOption
from paris.snapshot import importer_snapshot


def instantane(**surcharges):
    """Un instantané v4 minimal, à l'image de ce que publie le moteur."""
    base = {
        'version': 1,
        'exporte_le': '2026-10-09T09:14:51.448814+00:00',
        'competitions': [{'code': 'PL', 'nom': 'Premier League', 'pays': 'Angleterre',
                          'ordre': 20, 'sofascore_id': None}],
        'equipes': [
            {'slug': 'arsenal', 'nom': 'Arsenal', 'nom_court': 'Arsenal',
             'sofascore_id': None},
            {'slug': 'chelsea', 'nom': 'Chelsea', 'nom_court': 'Chelsea',
             'sofascore_id': None},
        ],
        'matchs': [{
            'sofascore_id': 900001,
            'competition_code': 'PL',
            'domicile_slug': 'arsenal',
            'exterieur_slug': 'chelsea',
            'coup_denvoi': '2026-10-18T14:00:00+00:00',
            'journee': '', 'statut': 'a_venir',
            'buts_dom': None, 'buts_ext': None,
            'buts_dom_mt': None, 'buts_ext_mt': None,
            'cotes': [], 'contexte': None,
            'ligne_totaux': 3.5,
            'cle_moteur': 'PL:2026-10-18:arsenal:chelsea',
            'analyse': {
                'buts_dom_attendus': 1.9, 'buts_ext_attendus': 1.2,
                'p1': 0.52, 'pn': 0.25, 'p2': 0.23,
                'score_probable': '2-1', 'profil': 'desequilibre',
                'marge_marche': 0.05, 'residu': 0.004,
                'version_moteur': '4.0.0',
                'douteuse': True,
                'source_cotes': 'forces_toutes_competitions',
                'exposition_lot': {'buts': 3},
                'ligne_totaux': 3.5,
                'options': [{
                    'famille': '1X2', 'code': '1X2_1', 'libelle': 'Arsenal gagne',
                    'probabilite': 0.52, 'cote_juste': 1.923,
                    'niveau': 'recommandee', 'origine': 'marche',
                    'resultat': 'attente',
                    'confiance': 71,
                    'explication': 'Nettement plus probable ici que sur les '
                                   'autres matchs du lot.',
                    'p_brute': 0.515, 'calibree': False,
                }],
            },
        }],
    }
    base.update(surcharges)
    return base


class ChampsMoteurTests(TestCase):
    """Tout ce que le moteur publie doit arriver en base, et rien d'autre."""

    def test_les_champs_v4_sont_importes(self):
        importer_snapshot(instantane())
        m = Match.objects.get(sofascore_id=900001)
        assert m.ligne_totaux == 3.5
        assert m.cle_moteur == 'PL:2026-10-18:arsenal:chelsea'

        a = m.analyse
        assert a.douteuse is True
        assert a.source_cotes == 'forces_toutes_competitions'
        assert a.exposition_lot == {'buts': 3}

        o = a.options.get(code='1X2_1')
        assert o.explication.startswith('Nettement plus probable')
        assert o.confiance == 71
        assert o.probabilite_brute == 0.515
        assert o.calibree is False

    def test_la_probabilite_affichee_est_celle_du_moteur(self):
        """Aucun arrondi, aucune transformation, aucun recalcul."""
        importer_snapshot(instantane())
        o = Option.objects.get(code='1X2_1')
        assert o.probabilite == 0.52
        assert o.cote_juste == 1.923

    def test_calcule_le_porte_la_date_du_moteur(self):
        """`auto_now` faisait passer une analyse de trois jours pour fraîche
        de deux heures, sur un champ dont le nom promet la date de calcul."""
        importer_snapshot(instantane())
        a = Analyse.objects.get()
        assert a.calcule_le.isoformat().startswith('2026-10-09T09:14:51')
        assert a.importe_le > a.calcule_le

    def test_une_ligne_de_totaux_autre_que_2_5_est_conservee(self):
        """35 % des rencontres ne sont pas cotées à 2,5. Ignorer la ligne
        faisait lire un prix sur 3,5 comme un prix sur 2,5."""
        importer_snapshot(instantane())
        assert Match.objects.get(sofascore_id=900001).ligne_totaux == 3.5


class VotesPreservesTests(TestCase):
    """`analyse.options.all().delete()` effaçait les votes en cascade."""

    def test_les_votes_survivent_a_un_import(self):
        importer_snapshot(instantane())
        o = Option.objects.get(code='1X2_1')
        u = User.objects.create_user('testeur', password='x')
        VoteOption.objects.create(option=o, user=u, choix='like')

        importer_snapshot(instantane())
        assert VoteOption.objects.count() == 1
        assert Option.objects.get(code='1X2_1').pk == o.pk

    def test_un_resultat_acquis_n_est_pas_reecrit(self):
        importer_snapshot(instantane())
        o = Option.objects.get(code='1X2_1')
        o.resultat = 'gagne'
        o.save(update_fields=['resultat'])

        importer_snapshot(instantane())
        assert Option.objects.get(code='1X2_1').resultat == 'gagne'

    def test_une_option_retiree_par_le_moteur_disparait(self):
        importer_snapshot(instantane())
        snap = instantane()
        snap['matchs'][0]['analyse']['options'] = []
        importer_snapshot(snap)
        assert Option.objects.filter(code='1X2_1').count() == 0


class ImportRobusteTests(TestCase):
    def test_un_code_inconnu_n_annule_pas_tout_l_import(self):
        """Avant : l'exception remontait dans une transaction atomique, TOUT
        l'import était annulé — scores et statuts des autres matchs compris —
        et l'exception était avalée en log. L'app servait alors l'ancien
        instantané indéfiniment, sans aucun signe."""
        snap = instantane()
        m = snap['matchs'][0]
        m['statut'] = 'termine'
        m['buts_dom'], m['buts_ext'] = 2, 1
        m['buts_dom_mt'], m['buts_ext_mt'] = 1, 0
        m['analyse']['options'].append({
            'famille': 'Marché futur', 'code': 'CODE_QUI_N_EXISTE_PAS_ENCORE',
            'libelle': 'Un marché que l’app ne connaît pas',
            'probabilite': 0.4, 'cote_juste': 2.5,
            'niveau': 'detail', 'origine': 'calcul', 'resultat': 'attente',
        })
        stats = importer_snapshot(snap)
        assert stats['matchs'] == 1
        # Le match est importé, son score est là, et l'option connue est réglée.
        assert Match.objects.get(sofascore_id=900001).buts_dom == 2
        assert Option.objects.get(code='1X2_1').resultat == 'gagne'
        # L'option inconnue reste en attente, sans faire tomber le reste.
        assert Option.objects.get(
            code='CODE_QUI_N_EXISTE_PAS_ENCORE').resultat == 'attente'

    def test_des_cotes_vides_n_effacent_pas_les_anciennes(self):
        """66 matchs sur 396 arrivaient avec `cotes: []`. L'import effaçait
        leurs cotes tout en gardant l'analyse : des tips affichés comme
        courants, et plus aucune cote derrière."""
        snap = instantane()
        snap['matchs'][0]['cotes'] = [{
            'bookmaker': 'draftkings', 'marche': '1X2', 'selection': '1',
            'valeur': 1.9, 'nb_sources': 1,
            'releve_le': '2026-10-09T08:00:00+00:00',
        }]
        importer_snapshot(snap)
        assert Match.objects.get(sofascore_id=900001).cotes.count() == 1

        snap2 = instantane()          # cotes: []
        importer_snapshot(snap2)
        assert Match.objects.get(sofascore_id=900001).cotes.count() == 1

    def test_une_analyse_que_le_moteur_ne_publie_plus_est_retiree(self):
        """Une analyse orpheline est invérifiable et impossible à rafraîchir."""
        importer_snapshot(instantane())
        assert Analyse.objects.count() == 1

        snap = instantane()
        snap['matchs'][0]['analyse'] = None
        stats = importer_snapshot(snap)
        assert Analyse.objects.count() == 0
        assert stats['analyses_perimees'] == 1

    def test_l_analyse_d_un_match_joue_est_conservee(self):
        """Son bilan est acquis : on ne le détruit pas."""
        snap = instantane()
        snap['matchs'][0]['statut'] = 'termine'
        snap['matchs'][0]['buts_dom'] = 2
        snap['matchs'][0]['buts_ext'] = 1
        importer_snapshot(snap)

        snap2 = instantane()
        snap2['matchs'][0]['statut'] = 'termine'
        snap2['matchs'][0]['buts_dom'] = 2
        snap2['matchs'][0]['buts_ext'] = 1
        snap2['matchs'][0]['analyse'] = None
        importer_snapshot(snap2)
        assert Analyse.objects.count() == 1


class JustificationTests(TestCase):
    """« Pourquoi ce tip » doit venir du moteur, pas d'un gabarit lexical."""

    def test_l_explication_du_moteur_est_servie(self):
        from paris.justification import justifier_option

        importer_snapshot(instantane())
        o = Option.objects.get(code='1X2_1')
        bloc = justifier_option(option=o, analyse=o.analyse,
                                domicile='Arsenal', exterieur='Chelsea')
        textes = [a['texte'] for a in bloc['arguments']]
        assert any('Nettement plus probable' in t for t in textes)

    def test_sans_explication_rien_n_est_affirme(self):
        """Les deux phrases retirées affirmaient ce que rien n'avait vérifié :
        « Marché + modèle alignés » et « Historique du duel cohérent »."""
        from paris.justification import _pourquoi

        texte = _pourquoi(libelle='Plus de 2,5 buts', famille='Total buts',
                          niveau='recommandee', contexte=None, analyse=None)
        assert 'alignés' not in texte
        assert 'cohérent' not in texte
        assert 'moteur' in texte.lower()


class TableauDeBordTests(TestCase):
    """Le filet n'est pas un tip : le moteur l'exclut explicitement."""

    def test_prudente_et_filet_sont_comptes_separement(self):
        from paris.dashboard import build_dashboard_stats

        importer_snapshot(instantane())
        a = Analyse.objects.get()
        for k in range(30):
            Option.objects.create(
                analyse=a, famille='Total buts', code=f'UN_P{k}',
                libelle='x', probabilite=0.7, cote_juste=1.4,
                niveau='prudente', origine='calcul',
                resultat='gagne' if k < 18 else 'perdu',
            )
        for k in range(30):
            Option.objects.create(
                analyse=a, famille='Total buts', code=f'OV_F{k}',
                libelle='Au moins 1 but', probabilite=0.94, cote_juste=1.06,
                niveau='filet', origine='calcul',
                resultat='gagne' if k < 28 else 'perdu',
            )
        d = build_dashboard_stats()
        assert d['n_tips'] == 30
        assert d['taux_tips'] == 60          # 18 / 30, et non 46 / 60
        assert d['n_filet'] == 30
        assert d['taux_filet'] == 93
