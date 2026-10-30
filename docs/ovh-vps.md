# Déploiement Zanalyze sur VPS OVH Cloud (recommandé)

Machine vide, avec Docker ou systemd. Si ce VPS fait déjà tourner le cluster k3s de Wayizé, suivez [ovh-cluster.md](ovh-cluster.md) : même Traefik, même Postgres, sous-domaine `zanalyze.gabomazone.com`.

Cible **production** : egress libre → ingest ESPN / snapshot Engine OK, TLS, cron, Postgres possible.

Deux chemins :

| Chemin | Quand l’utiliser | Doc |
|--------|------------------|-----|
| **Docker** (`make prod`) | Recommandé si tu as déjà utilisé `zanalyz-dev` en local | [docker.md](docker.md) |
| **systemd + nginx** | VPS classique sans Docker | sections ci-dessous |

Fichiers prêts : `deploy/gunicorn.conf.py`, `deploy/zanalyz.service`,
`deploy/nginx-zanalyz.conf`, `deploy/nginx-docker.conf`, `deploy/update.sh`,
`docker-compose.yml`, `Makefile`.

---

## A. Chemin Docker (proche avenir / recommandé)

Sur le VPS Ubuntu (Docker Engine + Compose plugin) :

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # puis reconnecte-toi en SSH

sudo mkdir -p /var/www/zanalyz
sudo chown "$USER":"$USER" /var/www/zanalyz
cd /var/www/zanalyz
git clone https://github.com/Stevy64/Zanalyze.git .

cp .env.example .env
nano .env
```

Renseigne au minimum :

```bash
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=…
DJANGO_ALLOWED_HOSTS=ton-domaine.com,www.ton-domaine.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://ton-domaine.com,https://www.ton-domaine.com
DJANGO_SSL=1
POSTGRES_PASSWORD=…   # fort
ZANALYZ_HTTP_PORT=80
```

```bash
# Optionnel si le réseau du build est fragile :
# make wheels && make prod-build
make prod-build
make superuser
make sync
```

Services : `zanalyz-web` (image `zanalyz-prod`), `zanalyz-db`, `zanalyz-nginx`.

TLS : Certbot sur l’hôte (proxy vers le port nginx), ou load-balancer OVH, puis `DJANGO_SSL=1`.  
Détails Makefile / health : [docker.md](docker.md).

Mises à jour :

```bash
cd /var/www/zanalyz
git pull
make prod-build
```

---

## B. Chemin classique (systemd + nginx, sans Docker)

Stack : **Ubuntu 22.04/24.04**, nginx, Gunicorn (systemd), Let’s Encrypt.

### 1. Prérequis

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev nginx git \
  build-essential libpq-dev certbot python3-certbot-nginx

sudo mkdir -p /var/www/zanalyz
sudo chown "$USER":www-data /var/www/zanalyz
cd /var/www/zanalyz
git clone https://github.com/Stevy64/Zanalyze.git .
```

### 2. Environnement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
nano .env
```

```bash
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=…   # python -c "import secrets; print(secrets.token_urlsafe(50))"
DJANGO_ALLOWED_HOSTS=ton-domaine.com,www.ton-domaine.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://ton-domaine.com,https://www.ton-domaine.com
DJANGO_SSL=1
```

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### 3. Gunicorn + systemd

```bash
sudo cp deploy/zanalyz.service /etc/systemd/system/zanalyz.service
sudo chown -R www-data:www-data /var/www/zanalyz
sudo chmod 640 /var/www/zanalyz/.env
sudo systemctl daemon-reload
sudo systemctl enable --now zanalyz
sudo systemctl status zanalyz
```

### 4. nginx + HTTPS

1. Remplace `zanalyz.example.com` dans `deploy/nginx-zanalyz.conf`.
2. DNS A → IP du VPS OVH.
3. Active le site :

```bash
sudo cp deploy/nginx-zanalyz.conf /etc/nginx/sites-available/zanalyz
sudo ln -sf /etc/nginx/sites-available/zanalyz /etc/nginx/sites-enabled/zanalyz
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
sudo certbot --nginx -d ton-domaine.com -d www.ton-domaine.com
```

### 5. Données + apprentissage moteur

Après chaque sync / règlement, le moteur **affine** `data/calibration.json`
à partir des tips déjà gagnés ou perdus.

```bash
cd /var/www/zanalyz
source .venv/bin/activate
set -a && source .env && set +a

python manage.py synchroniser_sofascore
python manage.py calculer_analyses
python manage.py regler_options --apprendre
```

Cron (toutes les 2 h) :

```cron
0 */2 * * * cd /var/www/zanalyz && . .venv/bin/activate && set -a && . ./.env && set +a && python manage.py synchroniser_sofascore --calculer && python manage.py regler_options --apprendre && python manage.py purger_chat >> /var/log/zanalyz-cron.log 2>&1
```

(`synchroniser_sofascore` n’ouvre plus de transaction pendant les appels HTTP ; le contexte H2H est opt-in via `--contexte`.)

### 6. Mises à jour

```bash
cd /var/www/zanalyz
sudo bash deploy/update.sh
```

---

## Checklist OVH

- [ ] DNS A → VPS
- [ ] `.env` prod (SECRET_KEY, ALLOWED_HOSTS, CSRF, SSL)
- [ ] Docker **ou** `zanalyz.service` + nginx + TLS
- [ ] Sync Engine / analyses + règlement
- [ ] PWA HTTPS OK (`/health/` → ok)

## Avant OVH : PythonAnywhere

Pour un premier essai UI/admin sans VPS : [pythonanywhere.md](pythonanywhere.md)  
(ingest live souvent limité sur le free tier — préférer le snapshot Engine).

## Autre hébergeur

Oracle Cloud Free Tier : [oracle-cloud.md](oracle-cloud.md).
