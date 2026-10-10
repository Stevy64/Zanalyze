# Architecture Zanalyze + Zanalyze Engine

Deux git :

- **Zanalyze** (ce repo `Zanalyze`) : PWA Django, admin, VIP
- **[Zanalyze Engine](https://github.com/Stevy64/Zanalyze-Engine)** : ESPN, moteur partagé v4.0.1, snapshot v1

Sur **PythonAnywhere**, Django importe le JSON produit par l’engine (`ZANALYZ_SYNC_LIVE=0`). Voir [engine.md](engine.md).

Sur **VPS Docker**, le worker importe le snapshot. `ZANALYZ_SYNC_LIVE=1` ajoute les scores et statuts en direct, sans recalculer les analyses importées. Le même paquet Engine est installé dans la web app et le service de calcul ; voir [Moteur unique](moteur-unique.md).

## Schéma (VPS Docker)

```text
                    ┌─────────────┐
   Internet ───────►│   nginx     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ zanalyz-web │  PWA + API + Admin
                    └──────┬──────┘
                           │ HTTP analyse (optionnel)
                    ┌──────▼──────┐
                    │ moteur      │  API du paquet Engine partagé
                    └─────────────┘

        ┌──────────────────────────────────────┐
        │ worker (~2 h)                        │
        │  importer_snapshot à chaque cycle    │
        │  SYNC_LIVE=1 : scores en complément  │
        │  puis regler_options + purger_chat   │
        └──────────────────────────────────────┘
```

## Schéma (PythonAnywhere + Engine)

```text
ESPN → Zanalyze-Engine (Actions / Oracle)
              ↓ exports/matchs.json (GitHub)
Zanalyze PA  ← importer_snapshot --url
```

## Granularité (volontairement limitée)

| Service | Image | Rôle |
|--------|-------|------|
| **nginx** | nginx | TLS/HTTP, static / media |
| **web** | `zanalyz-prod` | UI + API + admin |
| **moteur** | `zanalyz-moteur` | Calculs probabilités / tips |
| **worker** | `zanalyz-prod` | Pipeline autonome |
| **db** | postgres | Données |
| **redis** | redis | Lock jobs + présence Salon VIP |

Pas de découpage plus fin (auth service, etc.) : surcoût sans gain pour cette app.

## Variables clés

```bash
ZANALYZ_MOTEUR_URL=http://moteur:8001
ZANALYZ_REDIS_URL=redis://redis:6379/0
ZANALYZ_WORKER_INTERVAL=7200          # secondes entre deux pipelines
ZANALYZ_SYNC_LIVE=1                   # complément scores ; snapshot toujours importé
ZANALYZ_SNAPSHOT_URL=                 # raw GitHub du JSON engine
ZANALYZ_SYNC_PAGES=1
ZANALYZ_SYNC_CONTEXTE=0               # 1 = H2H/forme (plus lent)
```

Si `ZANALYZ_MOTEUR_URL` est vide, les calculs manuels Django exécutent **le même paquet Engine en local**. Une URL configurée exige un service de même version et ne déclenche pas de bascule automatique en cas de panne. Ces calculs concernent uniquement les matchs futurs hors snapshot.

`ENGINE_CALIBRATION_FILE` permet de fournir une courbe publiée par Engine ; en Docker, web et moteur consultent par défaut `/app/data/engine-calibration.json` sur le volume commun. Sans courbe publiée, les tables de référence du paquet s’appliquent.

## Lancer

```bash
# Prod
cp .env.example .env   # secrets
make prod-build        # web + moteur + worker + db + redis + nginx

# Dev (web + moteur ; worker optionnel)
make dev-d
make dev-worker        # profile Compose
```

## API moteur

- `GET  /health`
- `POST /v1/analyser` — lot de matchs + classement journée
- `POST /v1/analyser-un` — un match
- Docs OpenAPI : `http://moteur:8001/docs` (réseau Docker)

## Fiches clubs / logos

Chaîne côté serveur (noms de fournisseurs **non exposés** à l’UI) :

1. API calendrier principale  
2. Secours TheSportsDB (logos, forme, classement)  
3. Historique local en base  

Proxy logos : `GET /api/v1/equipes/<id>/logo/`

## PythonAnywhere

Pas de Docker : pas de worker container. Utilise les **Tasks** PA ou un cron
externe qui appelle les mêmes `manage.py` (voir [pythonanywhere.md](pythonanywhere.md)).
