# Zanalyze ↔ Zanalyze Engine

La PWA **Zanalyze** (ce repo, GitHub `Zanalyze`) affiche matchs et tips.  
Le calcul et l’ingest **ESPN** vivent dans un git **séparé** :

→ **[Zanalyze-Engine](https://github.com/Stevy64/Zanalyze-Engine)**  
  (copie locale : `../Zanalyze-Engine`)

## Pourquoi les scores / statuts doivent venir du moteur

L’app **ne scrape pas ESPN** en production (souvent bloqué). Le moteur publie
`exports/matchs.json` (Actions ~2 h). La PWA doit **importer** ce snapshot pour
avoir les statuts `termine`, scores et bilans OK/KO.

Chaîne automatique :

1. Worker (`deploy/worker-loop.sh`) : `importer_snapshot --url …` à chaque tour
2. API `POST /api/v1/sync/engine/` : tirée au démarrage PWA / pull-to-refresh
3. `GET /api/v1/matchs/` et `/info/` : refresh async si le snapshot a > ~10 min

```bash
# Manuel
python manage.py importer_snapshot --engine
# ou
python manage.py importer_snapshot --url https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json
```

Variables :

| Variable | Rôle |
|----------|------|
| `ZANALYZ_SNAPSHOT_URL` | URL du JSON engine (défaut = raw GitHub ci-dessus) |
| `ZANALYZ_SYNC_LIVE=0` | Sur PA : pas d’ingest SofaScore en plus |
| `ZANALYZ_SYNC_LIVE=1` | VPS : snapshot Engine **puis** complément SofaScore optionnel |
| `ZANALYZ_MOTEUR_URL` | Optionnel (VPS Docker). Sur PA, laisser vide |

Hors-ligne PWA : service worker (network-first + timeout → cache) + dernier
calendrier en `localStorage`.

Note : le champ JSON / DB `sofascore_id` est le **contrat snapshot v1** (ids ESPN). Ne pas le renommer côté PWA.

Doc Oracle moteur : [oracle.md](https://github.com/Stevy64/Zanalyze-Engine/blob/main/docs/oracle.md).
