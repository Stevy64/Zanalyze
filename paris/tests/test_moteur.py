"""Contrat de migration : l'app utilise exactement Zanalyze Engine.

Les tests mathématiques et de sélection résident dans Engine ; ici on teste
la compatibilité des anciens appels et la parité entre chemins d'exécution.
"""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from engine import moteur as reference
from engine.api_analyse import AnalyserRequest, post_analyser
from moteur_service.app import app
from paris import moteur
from paris.moteur_client import analyser_et_classer_journee


@pytest.mark.parametrize('cotes', [(1.90, 3.50, 4.00), (1.35, 5., 9.), (2.4, 3.2, 3.)])
def test_adaptateur_identique_au_moteur_existant(cotes):
    assert moteur.analyser(cotes, (1.9, 1.9), 'A', 'B') == reference.analyser(cotes, (1.9, 1.9, 2.5), 'A', 'B')


def test_aucun_algorithme_concurrent():
    assert moteur.classer_journee is reference.classer_journee
    assert moteur.matrice is reference.matrice
    assert moteur.corriger is reference.corriger
    assert moteur.choisir_trois is reference.choisir_options
    assert moteur.AnalyseInvalide is reference.AnalyseInvalide


def test_adaptateur_ligne_explicite():
    cotes = (1.9, 3.5, 4.)
    assert moteur.analyser(cotes, totaux=(1.9, 1.9, 3.5)) == reference.analyser(cotes, (1.9, 1.9, 3.5))
    with pytest.raises(moteur.AnalyseInvalide):
        moteur.analyser(cotes, (1.9, 1.9), totaux=(1.9, 1.9, 3.5))


LOT = [
    {'c1': 1.9, 'cn': 3.5, 'c2': 4., 'o25': 1.9, 'u25': 1.9, 'ref': 'a'},
    {'c1': 2.4, 'cn': 3.2, 'c2': 3., 'over': 1.9, 'under': 1.9, 'ligne': 3.5, 'ref': 'b'},
]


def test_parite_locale_http_et_moteur(settings):
    settings.ZANALYZ_MOTEUR_URL = ''
    attendu = post_analyser(AnalyserRequest(matchs=deepcopy(LOT))).model_dump(mode='json')['analyses']
    assert analyser_et_classer_journee(deepcopy(LOT)) == attendu
    client = TestClient(app)
    response = client.post('/v1/analyser', json={'matchs': LOT})
    assert response.status_code == 200
    assert response.json()['analyses'] == attendu
    # Exercer aussi la sérialisation et la lecture HTTP du client Django.
    settings.ZANALYZ_MOTEUR_URL = 'http://moteur:8001'
    def transport(req, timeout):
        from io import BytesIO
        body = json.loads(req.data)
        assert body['matchs'][0]['ligne'] == 2.5
        assert 'o25' not in body['matchs'][0]
        result = client.post('/v1/analyser', json=body)
        return BytesIO(result.content)
    with patch('urllib.request.urlopen', side_effect=transport):
        assert analyser_et_classer_journee(deepcopy(LOT)) == attendu


@pytest.mark.parametrize('totaux', [
    {'over': 1.9, 'under': 1.9}, {'o25': 1.9},
    {'over': 1.9, 'ligne': 2.5}, {'ligne': 2.5},
    {'o25': 1.9, 'u25': 1.9, 'ligne': 3.5},
    {'o25': 1.9, 'u25': 1.9, 'over': 1.9, 'under': 1.9},
])
def test_ligne_ambigue_refusee_local_et_http(settings, totaux):
    settings.ZANALYZ_MOTEUR_URL = ''
    match = {'c1': 1.9, 'cn': 3.5, 'c2': 4., **totaux}
    with pytest.raises(moteur.AnalyseInvalide):
        analyser_et_classer_journee([match])
    assert TestClient(app).post('/v1/analyser', json={'matchs': [match]}).status_code == 422


def test_ancien_service_refuse(settings):
    from io import BytesIO
    settings.ZANALYZ_MOTEUR_URL = 'http://moteur:8001'
    with patch('urllib.request.urlopen', return_value=BytesIO(b'{"version_moteur":"4.0.0","analyses":[]}')):
        with pytest.raises(moteur.AnalyseInvalide, match='Version moteur incompatible'):
            analyser_et_classer_journee(LOT)


def test_panne_distante_ne_bascule_pas_sur_autre_calibration(settings):
    settings.ZANALYZ_MOTEUR_URL = 'http://moteur:8001'
    with patch('urllib.request.urlopen', side_effect=TimeoutError):
        with pytest.raises(moteur.AnalyseInvalide, match='injoignable'):
            analyser_et_classer_journee(LOT)


def test_service_web_n_expose_pas_la_maintenance():
    client = TestClient(app)
    assert client.post('/v1/refresh', json={}).status_code == 404
    assert client.get('/v1/snapshot').status_code == 404
