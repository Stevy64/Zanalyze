"""Protection des analyses officielles face aux commandes historiques."""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from paris.models import Match, Cote
from paris.snapshot import importer_snapshot
from paris.tests.test_fidelite_moteur import instantane
from paris.management.commands.calculer_analyses import Command


@pytest.mark.django_db
def test_snapshot_jamais_recalcule():
    data = instantane()
    data['matchs'][0]['coup_denvoi'] = (timezone.now() + timedelta(days=1)).isoformat()
    importer_snapshot(data)
    m = Match.objects.get()
    avant = list(m.analyse.options.values())
    with patch('paris.moteur_client.analyser_et_classer_journee') as calcul:
        with pytest.raises(CommandError, match='non gérés'):
            call_command('calculer_analyses', journee=timezone.localtime(m.coup_denvoi).date().isoformat(), stdout=StringIO())
        calcul.assert_not_called()
    assert list(m.analyse.options.values()) == avant


@pytest.mark.django_db
def test_match_commence_jamais_recalcule():
    data = instantane()
    data['matchs'][0]['cle_moteur'] = ''
    data['matchs'][0]['coup_denvoi'] = (timezone.now() - timedelta(minutes=1)).isoformat()
    importer_snapshot(data)
    m = Match.objects.get()
    m.cle_moteur = ''
    m.save(update_fields=['cle_moteur'])
    with patch('paris.moteur_client.analyser_et_classer_journee') as calcul:
        with pytest.raises(CommandError):
            call_command('calculer_analyses', journee=timezone.localtime(m.coup_denvoi).date().isoformat(), stdout=StringIO())
        calcul.assert_not_called()


@pytest.mark.django_db
def test_derniere_verification_avant_sauvegarde():
    importer_snapshot(instantane())
    m = Match.objects.get()
    # Même un résultat de calcul déjà reçu ne peut écraser le snapshot.
    assert Command()._sauver(m, {}) == 0


@pytest.mark.django_db
def test_commande_transmet_ligne_reelle():
    importer_snapshot(instantane())
    m = Match.objects.get()
    for marche, selection, valeur in [('1X2','1',1.9),('1X2','N',3.5),('1X2','2',4.),('OU3.5','over',1.8),('OU3.5','under',2.1)]:
        Cote.objects.create(match=m, bookmaker='test', marche=marche, selection=selection, valeur=valeur, releve_le=timezone.now())
    _, totaux = Command()._cotes(m)
    assert totaux == (1.8, 2.1, 3.5)


@pytest.mark.django_db
def test_ancien_snapshot_sans_cle_est_aussi_protege():
    data = instantane()
    data['matchs'][0].pop('cle_moteur')
    importer_snapshot(data)
    assert Match.objects.get().cle_moteur == 'snapshot:900001'
