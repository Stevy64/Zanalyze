# Zanalyze

PWA d’aide à la décision pour les paris football. Affiche des **chances** et une **cote juste**.  
Ne prend pas de paris, ne se connecte à aucun bookmaker, ne promet aucun gain.

Stack : **Django 5 + DRF** (PWA Alpine). Les modèles v3.1 et l’ingest live (ESPN) sont dans le git séparé **[Zanalyze Engine](https://github.com/Stevy64/Zanalyze-Engine)** — voir [docs/engine.md](docs/engine.md).

---

## Prise en main rapide (local)

### Option A — Docker (recommandé)

```bash
git clone https://github.com/Stevy64/Zanalyze.git
cd Zanalyze
cp .env.example .env

# Si pip/DNS flaky dans Docker Desktop (Windows) :
make wheels-win          # remplit ./wheels/ (gitignore)

make dev-d               # web :8000 + moteur :8001 + redis
make migrate-dev
make superuser-dev
make sync-dev            # calendrier + analyses
```

- App : http://127.0.0.1:8000/  
- Admin : http://127.0.0.1:8000/admin/  
- Santé : http://127.0.0.1:8000/health/ et http://127.0.0.1:8001/health  

Worker autonome (sync périodique) :

```bash
make dev-worker
```

### Option B — Python local

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate
# Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
# Données : Zanalyze Engine (`python -m engine refresh`) puis :
python manage.py importer_snapshot --source ../Zanalyze-Engine/exports/matchs.json
python manage.py runserver
```

Sans `ZANALYZ_MOTEUR_URL`, le moteur tourne **dans le process Django**.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

---

## Mise en production (résumé)

| Cible | Doc | Notes |
|-------|-----|--------|
| **VPS Docker (OVH / Oracle…)** | [docs/docker.md](docs/docker.md) + [docs/ovh-vps.md](docs/ovh-vps.md) | **Recommandé** — stack complète autonome |
| Feuille de route | [docs/deploy.md](docs/deploy.md) | Choix d’hébergeur |
| Architecture | [docs/architecture.md](docs/architecture.md) | web · moteur · worker · db · redis · nginx |
| **PythonAnywhere** | [docs/pythonanywhere.md](docs/pythonanywhere.md) | Import snapshot Engine |
| **Zanalyze Engine** | [docs/engine.md](docs/engine.md) | Git séparé, Actions gratuit / Oracle Always Free |

### Prod Docker en 5 commandes

```bash
cp .env.example .env
# Éditer : DJANGO_SECRET_KEY, POSTGRES_PASSWORD, ALLOWED_HOSTS, CSRF…

make prod-build          # nginx + web + moteur + worker + postgres + redis
make migrate
make superuser
# → http://TON_IP/  (port ZANALYZ_HTTP_PORT, défaut 80)
```

Le **worker** enchaîne toutes les ~2 h : sync (ingest live **ou** snapshot Engine) → règlement → purge chat.  
Détail variables : `.env.example` et [docs/architecture.md](docs/architecture.md).

---

## Fonctionnalités produit

- Matchs du jour / filtre compétition · tips **Prudente / Équilibrée / Audacieuse** + filet  
- Fiche club (forme, classement, récents) · justifications Premium  
- Salon Premium (messages + images, rétention 24 h, présence en ligne)  
- Pronostics Premium 1X2 · points / grades · classement  
- Propositions utilisateurs + % de votes par scénario  
- Admin Django (Premium, WhatsApp, sync)

Moteur d’analyse : [docs/moteur-v31.md](docs/moteur-v31.md).

---

## Documentation

| Doc | Contenu |
|-----|---------|
| [docs/getting-started.md](docs/getting-started.md) | Prise en main détaillée |
| [docs/deploy.md](docs/deploy.md) | Feuille de route déploiement |
| [docs/docker.md](docs/docker.md) | Dev & prod Docker / Makefile |
| [docs/architecture.md](docs/architecture.md) | Micro-services |
| [docs/ovh-vps.md](docs/ovh-vps.md) | VPS OVH |
| [docs/oracle-cloud.md](docs/oracle-cloud.md) | Oracle Cloud Free Tier |
| [docs/pythonanywhere.md](docs/pythonanywhere.md) | Hébergement sans Docker + **snapshot Git** des matchs |
| [docs/moteur-v31.md](docs/moteur-v31.md) | Calibration & sélection tips |
| [docs/format_import.md](docs/format_import.md) | Format JSON (tests / démo uniquement) |

```bash
make help                # liste des commandes
```

---

## Licence / usage

Usage personnel / projet privé. Les données calendrier et clubs proviennent d’APIs tierces ; l’app n’affiche pas leur nom côté utilisateur.
