# Zanalyze sur le cluster

Ce guide s'enchaîne après le guide Wayizé (`docs/premier-cluster.md` de ce dépôt-là). On le lit de haut en bas. Les numéros 1 à 9 sont ceux de Zanalyze. Ils ne reprennent pas les numéros du guide Wayizé.

Dans le terminal, on ne colle que le contenu d'un bloc de commandes (le cadre gris). Les titres, les phrases et les lignes « Ça a marché si » ne sont pas des commandes.

## Avant l'étape 1

Sur le VPS, une seule fois, le guide Wayizé a déjà fait :

- les étapes 1 à 7 (SSH, système, k3s, kubectl, Traefik, cert-manager, Let's Encrypt) ;
- l'étape 10.2 (le Postgres du namespace `donnees`).

Vérifiez, puis restez dans ce document :

```bash
kubectl get nodes
kubectl get clusterissuer letsencrypt
kubectl -n donnees get deploy postgres
```

Ça a marché si le nœud est `Ready`, l'émetteur `letsencrypt` est `True`, et le déploiement `postgres` existe. Sinon, revenez au guide Wayizé, terminez ces étapes, et revenez ici à l'étape 1.

Les commandes se lancent sur le VPS. Si `whoami` affiche `root`, enlevez `sudo`.

Zanalyze, c'est quatre processus de la même image, plus Redis :

| Processus | Rôle | Publié sur Internet |
| --- | --- | --- |
| `zanalyze-web` | Le site. Gunicorn en local dans le pod, nginx sert `/media/`. WhiteNoise sert `/static/`. | Oui, `zanalyze.gabomazone.com` |
| `zanalyze-moteur` | Le calcul, port 8001 | Non. Le site l'appelle en `http://moteur:8001` |
| `zanalyze-worker` | Snapshot, scores, règlement, purges, toutes les 2 h | Non |
| `redis` | Verrou du worker | Non |

La base s'appelle `zanalyze`. Le disque `zanalyze-data` garde la calibration. Le disque `zanalyze-media` garde les images. Un seul nœud, un worker gunicorn.

## 1. Namespace

```bash
kubectl create namespace zanalyze
kubectl get namespaces
```

Ça a marché si `zanalyze` apparaît.

## 2. Nom de domaine

Même IPv4 que Wayizé. Dans la zone `gabomazone.com`, une entrée, pas deux :

| Champ | Valeur |
| --- | --- |
| Sous-domaine | `zanalyze` |
| Type | `A` |
| Cible | l'IPv4 du VPS (`dig +short wayize.gabomazone.com`) |
| TTL | 300 le temps de la mise en place |

```bash
dig +short zanalyze.gabomazone.com
```

Ça a marché si la commande affiche exactement cette IPv4. Ne passez pas à l'étape 6 tant que ce n'est pas le cas : le certificat en a besoin. Vous pouvez continuer les étapes 3, 4 et 5 en attendant.

## 3. Base de données

Le Postgres de l'étape 10.2 du guide Wayizé tourne déjà. On ajoute un utilisateur et une base. Pas un second Postgres.

```bash
APP_PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
kubectl -n donnees exec -i deploy/postgres -- psql -U postgres -v ON_ERROR_STOP=1 <<SQL
CREATE USER zanalyze WITH PASSWORD '${APP_PW}';
CREATE DATABASE zanalyze OWNER zanalyze;
SQL
```

Gardez `APP_PW` jusqu'à l'étape 5, qui le fera disparaître. Si `psql` dit que l'utilisateur existe, ne relancez pas le `CREATE` : le mot de passe déjà posé est le bon.

Ça a marché si `psql` répond deux fois `CREATE`.

## 4. Image

Faites le choix A ou le choix B, pas les deux. Notez la lettre : elle revient aux étapes 6 et 9.

Le dépôt doit contenir `deploy/k8s/` et `deploy/Dockerfile.zanalyze`. Poussez-les sur `main` avant de cloner.

### Choix A — GitHub Actions

GitHub construit l'image et la dépose sur GHCR. Le VPS la télécharge.

```bash
sudo mkdir -p /srv/zanalyze
sudo chown "$USER:$USER" /srv/zanalyze
git clone https://github.com/Stevy64/Zanalyze.git /srv/zanalyze
cd /srv/zanalyze
mkdir -p .github/workflows
cp deploy/zanalyze-image.yml .github/workflows/zanalyze-image.yml
git add .github/workflows/zanalyze-image.yml
git commit -m "Build the Zanalyze image on GHCR."
git push origin main
```

Si `git push` demande un mot de passe, c'est un jeton GitHub, pas celui du VPS. Ne l'écrivez pas dans le dépôt.

Ouvrez l'onglet Actions. Le job doit devenir vert. L'image s'appelle `ghcr.io/stevy64/zanalyze`, étiquette `main`.

Rendez le paquet `zanalyze` public (réglage du paquet sur GitHub), puis :

```bash
sudo k3s ctr images pull ghcr.io/stevy64/zanalyze:main
```

Ça a marché si la commande se termine sans `unauthorized`.

Si le paquet reste privé, un jeton qui peut seulement lire les paquets (`read:packages`), sur le VPS et pas dans git :

```bash
read -rs GHCR_TOKEN
kubectl -n zanalyze create secret docker-registry ghcr \
  --docker-server=ghcr.io \
  --docker-username=Stevy64 \
  --docker-password="$GHCR_TOKEN"
unset GHCR_TOKEN
```

Ajoutez alors, sous `spec.template.spec` de chaque Deployment et du Job dans `deploy/k8s/` :

```yaml
imagePullSecrets:
  - name: ghcr
```

Passez à l'étape 5.

### Choix B — Construire sur le VPS

Docker construit l'image. k3s l'exécute. Pas de workflow, pas de GHCR.

```bash
sudo apt install -y docker.io
sudo mkdir -p /srv/zanalyze
sudo chown "$USER:$USER" /srv/zanalyze
if [ ! -d /srv/zanalyze/.git ]; then
  git clone https://github.com/Stevy64/Zanalyze.git /srv/zanalyze
fi
cd /srv/zanalyze
git pull --ff-only
sudo docker build -f deploy/Dockerfile.zanalyze -t zanalyze:1 .
sudo docker save zanalyze:1 | sudo k3s ctr images import -
sudo k3s ctr images ls | grep zanalyze
```

Ça a marché si `grep` affiche `docker.io/library/zanalyze:1`.

Passez à l'étape 5. À l'étape 6, la commande sera `zanalyze-deploy local` : elle remplace en mémoire `ghcr.io/stevy64/zanalyze:main` par `docker.io/library/zanalyze:1`, et `imagePullPolicy: Always` par `Never`. Les fichiers du dépôt ne changent pas.

## 5. Variables

Une clé Django, le mot de passe de l'étape 3. `DJANGO_SECURE_SSL_REDIRECT=0` : Traefik termine déjà le TLS. Les cookies restent sûrs parce que `DJANGO_SSL=1`. `localhost` sert à la sonde du pod. L'Ingress n'accepte que `zanalyze.gabomazone.com`.

Zanalyze lit l'hôte, l'utilisateur, le mot de passe et le nom dans `DJANGO_DB_URL`. Le paramètre `sslmode` de cette URL est ignoré : le Postgres n'est pas publié.

```bash
WEB_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
sudo mkdir -p /etc/zanalyze
sudo tee /etc/zanalyze/app.env >/dev/null <<EOF
DJANGO_SETTINGS_MODULE=config.settings
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=${WEB_KEY}
DJANGO_ALLOWED_HOSTS=zanalyze.gabomazone.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://zanalyze.gabomazone.com
DJANGO_SSL=1
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_LOG_LEVEL=INFO
DJANGO_DB_URL=postgresql://zanalyze:${APP_PW}@postgres.donnees.svc.cluster.local:5432/zanalyze
ZANALYZ_REDIS_URL=redis://redis:6379/0
ZANALYZ_MOTEUR_URL=http://moteur:8001
ZANALYZ_SYNC_LIVE=1
ZANALYZ_WORKER_INTERVAL=7200
ZANALYZ_SYNC_PAGES=1
ZANALYZ_SYNC_PASSES=1
ZANALYZ_SYNC_CONTEXTE=0
ENGINE_CALIBRATION_FILE=/app/data/engine-calibration.json
EOF
sudo chmod 600 /etc/zanalyze/app.env
unset WEB_KEY APP_PW
sudo k3s kubectl -n zanalyze create secret generic zanalyze --from-env-file=/etc/zanalyze/app.env
```

Si `create secret` répond `already exists`, supprimez-le puis recréez-le. Ne commitez pas `/etc/zanalyze/app.env`.

SingPay et WhatsApp ne sont pas nécessaires pour ouvrir le site. Leurs noms sont dans `deploy/cluster.env.example`. On les ajoute plus tard dans le même fichier, on recrée le Secret, puis on relance l'étape 9.

Ça a marché si `kubectl -n zanalyze get secrets` liste `zanalyze`.

## 6. Lancer

```bash
sudo install -m 755 /srv/zanalyze/deploy/k8s/update.sh /usr/local/bin/zanalyze-deploy
```

Si vous avez choisi A à l'étape 4 :

```bash
zanalyze-deploy
```

Si vous avez choisi B à l'étape 4 :

```bash
zanalyze-deploy local
```

Le script attend Redis, joue la migration, puis lance le moteur, le site et le worker. Si la migration échoue, il s'arrête avant de redémarrer les pods.

```bash
kubectl -n zanalyze logs job/zanalyze-migrate
```

Ça a marché si la commande `zanalyze-deploy` se termine sans erreur, et si les trois `rollout` disent `successfully rolled out`.

## 7. Vérifier

Le certificat met souvent une minute. Relancez la première commande jusqu'à `READY` = `True`.

```bash
kubectl -n zanalyze get certificate
curl -fsS https://zanalyze.gabomazone.com/health/
```

Ça a marché si `curl` affiche `"status": "ok"` et `"app": "zanalyze"`.

Le moteur n'a pas d'adresse publique :

```bash
kubectl -n zanalyze exec deploy/zanalyze-web -c gunicorn -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://moteur:8001/health').read().decode())"
```

La réponse contient `"service": "zanalyze-engine"`.

Si le certificat reste `False` : `kubectl -n zanalyze describe certificate zanalyze-tls`. La cause la plus fréquente est un DNS qui ne pointe pas encore vers le VPS, ou le port 80 fermé.

## 8. Compte administrateur

```bash
kubectl -n zanalyze exec -it deploy/zanalyze-web -c gunicorn -- python manage.py createsuperuser
```

Ouvrez `https://zanalyze.gabomazone.com/` puis `https://zanalyze.gabomazone.com/admin/`.

Le worker importe le snapshot Engine dès son démarrage, puis toutes les deux heures.

```bash
kubectl -n zanalyze logs deploy/zanalyze-worker
kubectl -n zanalyze logs deploy/zanalyze-web -c gunicorn
kubectl -n zanalyze logs deploy/zanalyze-moteur
```

## 9. Mettre à jour

### Si vous aviez choisi A

Quand le job Actions est vert :

```bash
cd /srv/zanalyze
git pull --ff-only
zanalyze-deploy
curl -fsS https://zanalyze.gabomazone.com/health/
```

`imagePullPolicy: Always` retélécharge l'étiquette `main`. Pour revenir à un commit, remplacez `:main` par le SHA affiché dans Actions, dans le Job et dans chaque conteneur qui utilise l'image Zanalyze, puis `kubectl apply` et `kubectl rollout status`.

### Si vous aviez choisi B

```bash
cd /srv/zanalyze
git pull --ff-only
sudo docker build -f deploy/Dockerfile.zanalyze -t zanalyze:1 .
sudo docker save zanalyze:1 | sudo k3s ctr images import -
zanalyze-deploy local
curl -fsS https://zanalyze.gabomazone.com/health/
```

## À ne pas faire

- Refaire les étapes 1 à 7 du guide Wayizé, ni installer un second Postgres.
- Publier 8000, 8001 ou 6379.
- Activer `ufw`.
- Commiter `/etc/zanalyze/app.env`, ou réutiliser le Secret `wayize`.
- Lancer `zanalyze-deploy` sans `local` si l'image a été construite sur le VPS : k3s irait chercher `ghcr.io` alors que l'image s'appelle `zanalyze:1`.
- Relancer `CREATE USER` si la base existe déjà.
