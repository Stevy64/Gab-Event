# Gab Event sur le cluster

Ce guide s'enchaîne après le guide Wayizé (`docs/premier-cluster.md` du dépôt Wayizé). On le lit de haut en bas. Les numéros 1 à 9 sont ceux de Gab Event. Ils ne reprennent pas les numéros du guide Wayizé.

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

Ça a marché si le nœud est `Ready`, l'émetteur `letsencrypt` est `True`, et le déploiement `postgres` existe. Sinon, terminez ces étapes dans le guide Wayizé, puis revenez ici à l'étape 1.

Les commandes se lancent sur le VPS. Si `whoami` affiche `root`, enlevez `sudo`.

Gab Event, c'est trois processus de la même image, plus Redis :

| Processus | Rôle | Publié sur Internet |
| --- | --- | --- |
| `gabevent-web` | Le site. Gunicorn en local dans le pod, nginx sert `/media/`. | Oui, `gabevent.gabomazone.com` |
| `gabevent-worker` | Celery, un processus | Non |
| `gabevent-beat` | Expiration des événements, une fois par heure | Non. Un seul exemplaire |
| `redis` | Courtier Celery | Non |

La base s'appelle `gabevent`. Gab Event lit `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER` et `POSTGRES_PASSWORD`, pas une URL. Le disque `gabevent-media` (2 Gio) garde affiches et images, sur le pod web seulement.

`DEBUG=0` coupe le paiement simulé. Les invitations fonctionnent sans SingPay. La billetterie payante attend les identifiants, ajoutés à l'étape 5 une fois le site ouvert, ou dès maintenant si vous les avez.

## 1. Namespace

```bash
kubectl create namespace gabevent
kubectl get namespaces
```

Ça a marché si `gabevent` apparaît.

## 2. Nom de domaine

Même IPv4 que Wayizé. Dans la zone `gabomazone.com`, une entrée, pas deux :

| Champ | Valeur |
| --- | --- |
| Sous-domaine | `gabevent` |
| Type | `A` |
| Cible | l'IPv4 du VPS (`dig +short wayize.gabomazone.com`) |
| TTL | 300 le temps de la mise en place |

```bash
dig +short gabevent.gabomazone.com
```

Ça a marché si la commande affiche exactement cette IPv4. Le certificat de l'étape 7 en a besoin. Les étapes 3, 4 et 5 peuvent avancer pendant l'attente.

## 3. Base de données

```bash
APP_PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
kubectl -n donnees exec -i deploy/postgres -- psql -U postgres -v ON_ERROR_STOP=1 <<SQL
CREATE USER gabevent WITH PASSWORD '${APP_PW}';
CREATE DATABASE gabevent OWNER gabevent;
SQL
```

Gardez `APP_PW` jusqu'à l'étape 5. Si l'utilisateur existe déjà, ne relancez pas le `CREATE`.

Ça a marché si `psql` répond deux fois `CREATE`.

## 4. Image

Faites le choix A ou le choix B, pas les deux. Notez la lettre : elle revient aux étapes 6 et 9.

Le dépôt doit contenir `deploy/k8s/` et `deploy/Dockerfile.gabevent`. Poussez-les sur `main` avant de cloner.

### Choix A — GitHub Actions

```bash
sudo mkdir -p /srv/gabevent
sudo chown "$USER:$USER" /srv/gabevent
git clone https://github.com/Stevy64/Gab-Event.git /srv/gabevent
cd /srv/gabevent
mkdir -p .github/workflows
cp deploy/gabevent-image.yml .github/workflows/gabevent-image.yml
git add .github/workflows/gabevent-image.yml
git commit -m "Build the Gab Event image on GHCR."
git push origin main
```

Si `git push` demande un mot de passe, c'est un jeton GitHub. Ne l'écrivez pas dans le dépôt.

L'onglet Actions doit devenir vert. L'image s'appelle `ghcr.io/stevy64/gabevent`, étiquette `main`. Rendez le paquet public, puis :

```bash
sudo k3s ctr images pull ghcr.io/stevy64/gabevent:main
```

Ça a marché si la commande se termine sans `unauthorized`.

Si le paquet reste privé :

```bash
read -rs GHCR_TOKEN
kubectl -n gabevent create secret docker-registry ghcr \
  --docker-server=ghcr.io \
  --docker-username=Stevy64 \
  --docker-password="$GHCR_TOKEN"
unset GHCR_TOKEN
```

Ajoutez `imagePullSecrets: [{name: ghcr}]` sous `spec.template.spec` de chaque Deployment et du Job. Passez à l'étape 5.

### Choix B — Construire sur le VPS

```bash
sudo apt install -y docker.io
sudo mkdir -p /srv/gabevent
sudo chown "$USER:$USER" /srv/gabevent
if [ ! -d /srv/gabevent/.git ]; then
  git clone https://github.com/Stevy64/Gab-Event.git /srv/gabevent
fi
cd /srv/gabevent
git pull --ff-only
sudo docker build -f deploy/Dockerfile.gabevent -t gabevent:1 .
sudo docker save gabevent:1 | sudo k3s ctr images import -
sudo k3s ctr images ls | grep gabevent
```

Ça a marché si `grep` affiche `docker.io/library/gabevent:1`.

Passez à l'étape 5. À l'étape 6, la commande sera `gabevent-deploy local`.

## 5. Variables

`PUBLIC_BASE_URL` est en `https` : les cookies sont sûrs, et les retours de paiement utilisent cette adresse. `BEHIND_PROXY=1` fait lire `X-Forwarded-Proto`. `localhost` ne sert qu'à la sonde.

```bash
WEB_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
sudo mkdir -p /etc/gabevent
sudo tee /etc/gabevent/app.env >/dev/null <<EOF
DJANGO_SETTINGS_MODULE=config.settings
DEBUG=0
SECRET_KEY=${WEB_KEY}
ALLOWED_HOSTS=gabevent.gabomazone.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://gabevent.gabomazone.com
PUBLIC_BASE_URL=https://gabevent.gabomazone.com
BEHIND_PROXY=1
ALLOW_MOCK_PAYMENTS=0
POSTGRES_HOST=postgres.donnees.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_DB=gabevent
POSTGRES_USER=gabevent
POSTGRES_PASSWORD=${APP_PW}
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
EOF
sudo chmod 600 /etc/gabevent/app.env
unset WEB_KEY APP_PW
sudo k3s kubectl -n gabevent create secret generic gabevent --from-env-file=/etc/gabevent/app.env
```

Ça a marché si `kubectl -n gabevent get secrets` liste `gabevent`.

Pour encaisser plus tard : ajoutez dans `/etc/gabevent/app.env` les clés `SINGPAY_API_KEY`, `SINGPAY_API_SECRET`, `SINGPAY_MERCHANT_ID`, `SINGPAY_DISBURSEMENT_ID` et `SINGPAY_ENVIRONMENT=production`, supprimez le Secret, recréez-le, puis refaites l'étape 9. Le webhook à déclarer est `https://gabevent.gabomazone.com/payments/webhook/singpay/`.

L'e-mail de mot de passe oublié (`EMAIL_HOST` et la suite, voir `deploy/cluster.env.example`) se pose de la même façon. Sans `EMAIL_HOST`, le message part dans les journaux du pod.

## 6. Lancer

```bash
sudo install -m 755 /srv/gabevent/deploy/k8s/update.sh /usr/local/bin/gabevent-deploy
```

Si vous avez choisi A à l'étape 4 :

```bash
gabevent-deploy
```

Si vous avez choisi B à l'étape 4 :

```bash
gabevent-deploy local
```

Le script attend Redis, joue la migration, puis lance le site, le worker et beat. Si la migration échoue, il s'arrête.

```bash
kubectl -n gabevent logs job/gabevent-migrate
```

Ça a marché si la commande se termine sans erreur.

## 7. Vérifier

La sonde `/health/` interroge la base. Tant que Postgres ne répond pas, le pod n'est pas prêt.

```bash
kubectl -n gabevent get certificate
curl -fsS https://gabevent.gabomazone.com/health/
```

Ça a marché si `gabevent-tls` est `READY` = `True` et si `curl` affiche `"status": "ok"`, `"database": "ok"` et `"service": "gabevent"`.

S'il reste `False` : `kubectl -n gabevent describe certificate gabevent-tls`.

## 8. Compte administrateur

```bash
kubectl -n gabevent exec -it deploy/gabevent-web -c gunicorn -- python manage.py createsuperuser
```

Ouvrez `https://gabevent.gabomazone.com/` puis `https://gabevent.gabomazone.com/admin/`.

```bash
kubectl -n gabevent logs deploy/gabevent-web -c gunicorn
kubectl -n gabevent logs deploy/gabevent-worker
kubectl -n gabevent logs deploy/gabevent-beat
```

## 9. Mettre à jour

### Si vous aviez choisi A

Quand le job Actions est vert :

```bash
cd /srv/gabevent
git pull --ff-only
gabevent-deploy
curl -fsS https://gabevent.gabomazone.com/health/
```

Pour revenir à un commit, remplacez `:main` par le SHA du job, dans le Job de migration et dans chaque conteneur de l'image, puis appliquez les manifests.

### Si vous aviez choisi B

```bash
cd /srv/gabevent
git pull --ff-only
sudo docker build -f deploy/Dockerfile.gabevent -t gabevent:1 .
sudo docker save gabevent:1 | sudo k3s ctr images import -
gabevent-deploy local
curl -fsS https://gabevent.gabomazone.com/health/
```

## À ne pas faire

- Refaire les étapes 1 à 7 du guide Wayizé, ni installer un second Postgres.
- Publier 8000 ou 6379, ni donner un Ingress à Celery.
- Activer `ufw`.
- Commiter `/etc/gabevent/app.env`, laisser `ALLOW_MOCK_PAYMENTS=1`, ou réutiliser le Secret `wayize`.
- Lancer `gabevent-deploy` sans `local` si l'image a été construite sur le VPS.
- Lancer deux exemplaires de `gabevent-beat`.
- Relancer `CREATE USER` si la base existe déjà.
