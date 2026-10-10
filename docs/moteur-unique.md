# Consolidation des moteurs Zanalyze — 10 octobre 2026

## Décision

Conserver Zanalyze Engine et distribuer son code à la web app comme un paquet
Python versionné. Retirer les algorithmes copiés dans `paris.moteur` et
`paris.calibrage`. Les anciens imports restent valides grâce à des adaptateurs.
Le service Docker `moteur` reste utilisable : il exécute désormais ce même
paquet et le même contrat API. Il ne constitue plus un deuxième moteur.

L'historique Git montre que le dépôt Engine est issu du modèle embarqué v3.1,
puis a évolué vers v4. La copie Django affichait également « 4.0.0 » alors
qu'elle conservait les règles antérieures. La version seule masquait donc
la divergence. La distribution commune porte désormais la version 4.0.1.

## Évaluation et améliorations conservées

La comparaison synthétique emploie les mêmes tables de calibration et des
cotes cohérentes générées depuis la matrice, avec une marge de 4 %.
Les résultats sont conservés dans `comparaison-moteurs.json`.

| Ligne réellement cotée | Total attendu ancienne copie | Total attendu Engine |
|---|---:|---:|
| 2,5 | 2,6526 | 2,6526 |
| 3,5 | 2,1507 | 3,0021 |
| 4,5 | 2,6143 | 4,5031 |

La copie locale imposait 2,5 et introduisait donc une incohérence dès qu'on
lui transmettait les prix d'une autre ligne. L'API commune conserve les champs
historiques `o25/u25`, mais les convertit explicitement en ligne 2,5. Les champs
`over/under` exigent une ligne ; les couples incomplets ou contradictoires sont
refusés. Les commandes Django transmettent désormais la ligne réelle.

Sont également conservés : calibration par marché, contrôle de cohérence,
recommandation par utilité, limitation des propositions corrélées, confiance,
explications, historique figé, forces d'équipes pour les matchs sans marché,
apprentissage validé dans Engine et compétitions internationales.

Ces vérifications démontrent la cohérence de calcul et de contrat. Elles ne
constituent pas un nouveau test de précision prédictive sur des matchs réels.
Un mélange pondéré des deux copies n'est pas justifié : elles partagent le
même socle et l'une conserve des hypothèses corrigées par l'autre.

## Responsabilités et protections

- Engine collecte les données, calcule, apprend et publie les snapshots.
- La web app importe ces analyses et préserve leurs champs ; ses calculs
  manuels concernent uniquement les matchs futurs hors snapshot.
- Un verrou et une nouvelle vérification avant sauvegarde protègent un match
  importé ou commencé pendant un appel réseau. Les options réglées ne sont
  pas recalculées.
- Les anciens snapshots sans clé reçoivent un marqueur `snapshot:<id>` pour
  bénéficier de la même protection dès leur prochain import.
- Le worker live ne déclenche plus de recalcul après l'import. Son script est
  compatible avec `sh` ; les tableaux Bash qui le faisaient échouer ont été retirés.
- `apprendre_calibration` ne calcule plus de courbe concurrente : il renvoie
  une erreur explicite avec la commande Engine à utiliser.
- Un service HTTP d'une autre version est refusé. Une panne HTTP ne déclenche
  pas de bascule silencieuse vers une calibration potentiellement différente.

## Installation et maintenance

La wheel présente dans `vendor/` contient le code Engine et ses tables de
référence. Son manifeste indique la version et l'empreinte de chaque fichier.
Le test de distribution vérifie aussi les fichiers effectivement installés.
La construction Docker et l'installation habituelle via `requirements.txt`
installent ce paquet local, sans dépendre d'un dépôt frère ou de GitHub au démarrage.

Pour une nouvelle livraison : augmenter la version dans Engine, lancer
`python tools/build_web_package.py --web-repo ../Zanalyze` depuis son dépôt,
installer les dépendances de la web app et tester les deux projets ensemble.
Le paquet est construit depuis les sources de travail évaluées ; il ne prouve
pas qu'elles ont déjà été commitées ou publiées.

Les courbes apprises sont des données distinctes du code. En mode HTTP, le
service gère sa calibration. En mode local, `ENGINE_CALIBRATION_FILE` peut
pointer vers une copie de la même courbe publiée par Engine. Sans ce réglage,
les tables de référence du paquet s'appliquent. Les anciennes courbes Django
ne sont pas reprises automatiquement, car elles ont été apprises par un
processus différent. Les snapshots gardent les probabilités publiées par Engine.

Le déploiement doit reconstruire ensemble web, worker et service moteur,
appliquer les migrations déjà présentes, puis réimporter un snapshot Engine.
Les modifications locales ne constituent pas un déploiement en production.

## Recette finale locale

- Zanalyze Engine : 170 tests réussis.
- Web app avec la distribution finale installée : 132 tests réussis.
- Parité local / HTTP, anciens paramètres OU2.5, lignes explicites, refus des
  versions différentes, préservation des snapshots et matchs commencés : vérifiés.
- Empreintes du paquet et fichiers installés : identiques au manifeste.
- Vérifications Django et détection des migrations manquantes : aucune anomalie.
- Configuration Docker Compose et syntaxe `sh` du worker : valides.
- Schéma OpenAPI Engine : routes de calcul et de maintenance conservées.

Deux avertissements de dépréciation concernent les bibliothèques du client
HTTP de test ; aucun test n'échoue. Aucun service de production n'a été
reconstruit ou redémarré lors de cette intervention.
