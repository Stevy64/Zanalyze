# Prise en main — Zanalyze

Guide pour lancer le projet en local et comprendre le flux quotidien.

## 1. Prérequis

- Git, Python 3.11+ **ou** Docker Desktop / Engine  
- Sous Windows : `make` via Git Bash / WSL, ou recopier les commandes `docker compose` de [docker.md](docker.md)

## 2. Premier démarrage (Docker)

```bash
git clone https://github.com/Stevy64/Zanalyze.git
cd Zanalyze
cp .env.example .env
```

Si le build Docker échoue sur `pip install` (DNS) :

```bash
make wheels-win    # Windows + venv local
# ou make wheels   # Linux/macOS
```

Puis :

```bash
make dev-d
make migrate-dev
make superuser-dev
```

Ouvre http://127.0.0.1:8000/ et connecte-toi à `/admin/`.

### Remplir le calendrier

Préféré : snapshot **Zanalyze Engine** (voir [engine.md](engine.md)) :

```bash
python manage.py importer_snapshot --source ../Zanalyze-Engine/exports/matchs.json
# ou
python manage.py importer_snapshot --url https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json
```

Toujours possible en local (egress libre) :

```bash
make sync-dev
```

Équivalent manuel :

```bash
# Données via le snapshot Engine (recommandé) :
#   python -m engine refresh --provider espn --jours 21
#   python manage.py importer_snapshot --source ../Zanalyze-Engine/exports/matchs.json
docker compose -f docker-compose.dev.yml exec web \
  python manage.py importer_snapshot --source /app/exports/matchs.json
```

Contexte terrain (forme / H2H / absents) — plus lent, optionnel :

```bash
make sync-full-dev
```

## 3. Comptes & Premium

1. Créer un superuser (`make superuser-dev`).  
2. Dans l’admin : utilisateurs → profil → activer Premium (durée / expiration).  
3. Réglages site : numéro WhatsApp + message pour la demande Premium.

Rôles côté app :

| Catégorie | Accès |
|-----------|--------|
| Visiteur | Liste matchs, tips sans justifs |
| Membre | + votes / propositions ; bilans passés = Prudent + Sécurité (OK/KO) |
| Premium | + justifications, Nos Zanalyze, Salon Premium, bilans complets, pronostics / classement |
| Admin | staff Django + mêmes droits Premium |

## 4. Pages utiles

| URL | Rôle |
|-----|------|
| `/` | Matchs du jour |
| `/salon` | Chat Premium + classement |
| `/admin/` | Back-office |
| `/health/` | Sonde load-balancer |
| `:8001/health` | Sonde moteur (Docker) |

## 5. Développement sans Docker

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
pytest
```

Le moteur peut rester local (pas de `ZANALYZ_MOTEUR_URL`). Pour tester le micro-service :

```bash
uvicorn moteur_service.app:app --reload --port 8001
# .env : ZANALYZ_MOTEUR_URL=http://127.0.0.1:8001
```

## 6. Flux données (résumé)

```text
Sync calendrier / cotes
        ↓
Moteur v3.1 → tips (prudente / équilibrée / audacieuse / filet)
        ↓
App PWA + votes utilisateurs
        ↓
Règlement après match (+ apprentissage calibration)
```

Fiches clubs : chaîne de secours logos / forme si l’API calendrier principale est indisponible (détails techniques dans le code, non exposés à l’UI).

## 7. Commandes fréquentes

```bash
make help
make logs-dev
make logs-moteur
make health
make stop-dev
make clean                 # volumes / images (destructif)
```

## 8. Ensuite

- Déploiement : [deploy.md](deploy.md)  
- Prod Docker : [docker.md](docker.md)  
- Architecture : [architecture.md](architecture.md)
