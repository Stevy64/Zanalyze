# Déploiement — feuille de route

Objectif : une instance **autonome** (sync + analyses + règlement) avec le moins d’étapes possible.

## Choix recommandé

**VPS + Docker** (OVH, Oracle Cloud Free Tier, etc.)  
→ [docker.md](docker.md) puis [ovh-vps.md](ovh-vps.md) ou [oracle-cloud.md](oracle-cloud.md)

```bash
cp .env.example .env
# DJANGO_SECRET_KEY, POSTGRES_PASSWORD, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS

make prod-build
make migrate
make superuser
```

Services démarrés : **nginx · web · moteur · worker · postgres · redis**.  
Le worker boucle ~toutes les 2 h (voir `ZANALYZ_WORKER_INTERVAL`).

Vérifications :

```bash
curl http://127.0.0.1/health/
make logs-worker
make health
```

## Alternatives

| Cible | Quand | Doc |
|-------|--------|-----|
| **Cluster k3s** | Le VPS fait déjà tourner Wayizé | [ovh-cluster.md](ovh-cluster.md) |
| **OVH VPS** sans Docker | systemd + nginx + Gunicorn | [ovh-vps.md](ovh-vps.md) section B |
| **Oracle Cloud** | Free Tier, egress OK | [oracle-cloud.md](oracle-cloud.md) |
| **PythonAnywhere** | Prototype sans Docker | [pythonanywhere.md](pythonanywhere.md) — snapshot **Zanalyze Engine** |
| **Zanalyze Engine** | Ingest + modèles (git séparé) | [engine.md](engine.md) |
| **Local** | Dev | [getting-started.md](getting-started.md) |

## Checklist prod

- [ ] `.env` hors Git, secrets forts  
- [ ] `DJANGO_DEBUG=0`, SSL / HSTS si HTTPS  
- [ ] `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS`  
- [ ] Superuser créé  
- [ ] Première sync + analyses OK (`make logs-worker` ou sync manuelle)  
- [ ] WhatsApp VIP configuré (admin Réglages site)  
- [ ] Sauvegarde Postgres / volume data  

## Santé

`GET /health/` → `{"status":"ok","app":"zanalyz"}`  
Moteur : `GET http://moteur:8001/health` (réseau Docker)

Schéma des services : [architecture.md](architecture.md).
