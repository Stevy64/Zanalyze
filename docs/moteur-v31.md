> Archive historique v3.1. Pour le fonctionnement actuel, voir [Moteur unique](moteur-unique.md). Les commandes et chemins ci-dessous décrivent l’ancien système.

﻿# Moteur de pronostics — version 3.1 (intégré dans Zanalyze)

Modules portés dans `paris/` :

| Fichier | Rôle |
|---|---|
| `paris/moteur.py` | λ depuis cotes, marchés, sélection journée (plafond formes) |
| `paris/calibrage.py` | Calibration **marché par marché**, cohérence des complémentaires |
| `paris/calibration_par_marche.json` | 24 courbes (224 163 observations) |
| `paris/evaluation.py` | Règlement des codes d’options (y compris HCP −k, 2+) |

## Validé

- **Calibration par marché** : Brier hors échantillon 0,18782 (meilleure que famille v3.0 et que « rien »).
- **Cohérence** : paires complémentaires sommées à 100 % (écart ~0).
- **Diversification** : plafond de 3 occurrences d’une même forme sur une journée.

## Non injecté dans le calcul

Le **contexte** (forme, Elo, H2H, dispersion bookmakers) n’améliore pas la log-perte hors échantillon ; il reste informatif côté UI / justifications, pas dans `corriger()`.

Apprentissage local : `python manage.py apprendre_calibration` (overrides dans `data/calibration.json`, schéma `marche_v31`).
