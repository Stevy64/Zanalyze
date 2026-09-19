# Déployer Zanalyze sur PythonAnywhere

Guide **pas à pas** (compte Beginner ou payant).  
**Pas de Docker** sur PythonAnywhere — app WSGI classique.

> **Pourquoi aucun match ?** Sur le free tier, l’ingest live n’est pas fiable.
> La source de vérité est **[Zanalyze Engine](https://github.com/Stevy64/Zanalyze-Engine)**
> (GitHub Actions ou Oracle Always Free). PA **importe** seulement le snapshot.

Détail : [engine.md](engine.md).

---

## Données matchs via Zanalyze Engine (recommandé)

### A. Moteur (Actions / VPS / PC)

Le workflow du repo engine commit `exports/matchs.json` toutes les ~2 h.

### B. Sur PythonAnywhere (Scheduled task)

**Garder `ZANALYZ_SYNC_LIVE=0`.** Ce n’est **pas** nécessaire (ni recommandé) sur PA pour avoir scores/bilans à jour : PA n’ingest pas ESPN/SofaScore de façon fiable. La fraîcheur = snapshot Engine + import régulier.

Scheduled task (toutes les **2 h**, ex. `25 */2 * * *` — 10 min après le cron Engine) :

```bash
cd ~/Zanalyze
source ~/.virtualenvs/zanalyz/bin/activate
set -a && source .env && set +a
python manage.py importer_snapshot --url "$ZANALYZ_SNAPSHOT_URL"
```

`.env` PA :

```bash
ZANALYZ_SYNC_LIVE=0
# Pas de ZANALYZ_MOTEUR_URL — analyses déjà dans le snapshot
ZANALYZ_SNAPSHOT_URL=https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json
```

`raw.githubusercontent.com` est en général autorisé sur PA.

Recharge la page Matchs. Le filtre date doit correspondre au snapshot (`--jours 21` côté engine).

### Routine

| Fréquence | Action |
|-----------|--------|
| Engine (Actions) | sync ESPN + analyses + push JSON (~2 h) |
| PA (Scheduled task) | `importer_snapshot --url …` (~2 h) |

La PWA déclenche aussi un import async au chargement (`/api/v1/info/`), mais la **task PA** garantit la fraîcheur même sans visite.

### C. Purge rétention (quotidien)

Scheduled task PA (1×/jour, ex. `10 4 * * *`) :

```bash
cd ~/Zanalyze
source ~/.virtualenvs/zanalyz/bin/activate
set -a && source .env && set +a
python manage.py purger_retention
```

Effets :
- messages Salon > **24 h**
- matchs terminés > **1 mois**
- comptes inactifs > **6 mois** (hors staff)

Fallback manuel (PC) : `make sync-dev` puis `make snapshot-export-dev` dans **ce** repo.

---

## 1. Clone

```bash
cd ~
git clone https://github.com/Stevy64/Zanalyze.git
cd Zanalyze
```

---

## 2. Virtualenv + dépendances

Python **3.10** ou **3.11**.

```bash
cd ~/Zanalyze
python3.11 -m venv ~/.virtualenvs/zanalyz
source ~/.virtualenvs/zanalyz/bin/activate
pip install -U pip
pip install -r requirements.txt
```

---

## 3. `.env`

```bash
cp .env.example .env
nano .env
```

```bash
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=…   # secrets.token_urlsafe(50)
DJANGO_ALLOWED_HOSTS=TONUSER.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://TONUSER.pythonanywhere.com
DJANGO_SSL=1
DJANGO_SECURE_SSL_REDIRECT=0
ZANALYZ_SYNC_LIVE=0
# Pas de ZANALYZ_MOTEUR_URL — analyses déjà dans le snapshot
ZANALYZ_SNAPSHOT_URL=https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json
```

---

## 4. Migrate + static + snapshot

```bash
source ~/.virtualenvs/zanalyz/bin/activate
set -a && source .env && set +a
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createsuperuser   # si pas déjà fait
python manage.py importer_snapshot --url "$ZANALYZ_SNAPSHOT_URL"
```

Les **logos** sont des URLs CDN chargées par le **navigateur** (pas le serveur PA).  
Les **fiches club** (blason) viennent du champ embarqué dans le snapshot.  
« Consensus — » = pas encore de votes utilisateurs (normal).

---

## 5. Web app WSGI

1. **Web** → Manual configuration → même Python que le venv  
2. Source / working dir : `/home/TONUSER/Zanalyze`  
3. Virtualenv : `/home/TONUSER/.virtualenvs/zanalyz`  
4. WSGI :

```python
import os
import sys
from dotenv import load_dotenv

project_home = "/home/TONUSER/Zanalyze"
if project_home not in sys.path:
    sys.path.insert(0, project_home)
load_dotenv(os.path.join(project_home, ".env"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

5. **Static files** (Web → Static files) — **obligatoire** pour CSS/JS et fortement recommandé pour les images salon :

   Dans le dashboard PythonAnywhere → ton Web app → section **Static files** → **Enter URL** / **Enter path** :

   | URL | Directory |
   |-----|-----------|
   | `/static/` | `/home/TONUSER/Zanalyze/staticfiles` |
   | `/media/` | `/home/TONUSER/Zanalyze/media` |

   Puis clique **Reload** en haut de la page Web.

6. Créer le dossier media si besoin :

```bash
mkdir -p ~/Zanalyze/media
```

7. **Reload** — health : `/health/`

> Les images du Salon VIP sont stockées dans `media/salon/…`.
> Sans mapping `/media/` (ou sans le fallback Django `/media/`), les vignettes renvoient 404 en prod.

---

## Suite

Prod autonome Docker : [docker.md](docker.md) · [ovh-vps.md](ovh-vps.md)
