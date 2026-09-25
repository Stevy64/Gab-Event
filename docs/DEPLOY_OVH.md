# Livrer Gab Event sur OVH Cloud

Guide pas à pas, sans jargon inutile. Objectif : un site en ligne sur **votre nom de domaine**, avec Docker.

Vous aurez besoin :

- d’un **VPS OVH** (Ubuntu 24.04, 2 Go de RAM minimum)
- d’un **nom de domaine** (chez OVH ou ailleurs)
- du dépôt GitHub `https://github.com/Stevy64/Gab-Event.git`

---

## 1. Créer le VPS

1. Connectez-vous à [OVH Cloud](https://www.ovh.com/manager/).
2. Créez un **VPS** : Ubuntu 24.04, zone au plus près de vos utilisateurs.
3. Notez l’**adresse IP** et le mot de passe root (ou la clé SSH).
4. Dans l’onglet réseau, l’IP publique doit être visible.

Connectez-vous :

```bash
ssh root@ADRESSE_IP_DU_VPS
```

---

## 2. Pointer le nom de domaine

Dans la zone DNS du domaine, créez :

| Type | Nom | Cible |
|------|-----|--------|
| A | `@` | `ADRESSE_IP_DU_VPS` |
| A | `www` | `ADRESSE_IP_DU_VPS` |

Attendez 5 à 30 minutes. Vérifiez :

```bash
ping votredomaine.com
```

L’IP affichée doit être celle du VPS.

---

## 3. Préparer le serveur

Toujours en root sur le VPS :

```bash
apt-get update
apt-get install -y git curl
curl -fsSL https://raw.githubusercontent.com/Stevy64/Gab-Event/main/deploy/ovh-setup.sh | bash
```

Ou, si le dépôt est déjà cloné :

```bash
bash /opt/gab-event/deploy/ovh-setup.sh
```

Le script installe **Docker**, ouvre les ports **22 / 80 / 443**.

---

## 4. Installer l’application

```bash
git clone https://github.com/Stevy64/Gab-Event.git /opt/gab-event
cd /opt/gab-event
cp deploy/ovh.env.example .env
nano .env
```

Remplissez au minimum :

- `SECRET_KEY` — générez-la avec :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

- `ALLOWED_HOSTS=votredomaine.com,www.votredomaine.com`
- `CSRF_TRUSTED_ORIGINS=https://votredomaine.com,https://www.votredomaine.com`
- `PUBLIC_BASE_URL=https://votredomaine.com`
- `POSTGRES_PASSWORD` — un mot de passe long, différent de `SECRET_KEY`

Puis :

```bash
cd /opt/gab-event
docker compose up -d --build
```

Attendez que les conteneurs soient sains :

```bash
docker compose ps
curl http://127.0.0.1/health/
```

Vous devez voir `"status": "ok"`.

Créez le compte administrateur :

```bash
docker compose exec gabevent-web python manage.py createsuperuser
```

Ouvrez `http://ADRESSE_IP_DU_VPS/` dans le navigateur. La page d’accueil doit s’afficher.

---

## 5. Activer le HTTPS (certificat gratuit)

Quand le domaine pointe bien vers le VPS :

```bash
apt-get install -y certbot
mkdir -p /var/www/certbot
certbot certonly --webroot -w /var/www/certbot -d votredomaine.com -d www.votredomaine.com
```

Si Certbot ne trouve pas le dossier (nginx Docker n’expose pas encore le webroot), utilisez le mode temporaire :

```bash
docker compose stop gabevent-nginx
certbot certonly --standalone -d votredomaine.com -d www.votredomaine.com
docker compose start gabevent-nginx
```

Ensuite :

1. Copiez le modèle SSL :

```bash
cp /opt/gab-event/nginx/conf.d/gabevent-ssl.conf.example /opt/gab-event/nginx/conf.d/gabevent-ssl.conf
```

2. Remplacez `VOTRE_DOMAINE` dans ce fichier par `votredomaine.com`.
3. Désactivez l’ancien fichier HTTP pour éviter le conflit :

```bash
mv /opt/gab-event/nginx/conf.d/gabevent.conf /opt/gab-event/nginx/conf.d/gabevent.conf.off
```

4. Dans `docker-compose.yml`, ajoutez le port **443** et les certificats au service `gabevent-nginx` :

```yaml
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - static_files:/app/staticfiles:ro
      - media_files:/app/media:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - /var/www/certbot:/var/www/certbot:ro
```

5. Relancez :

```bash
cd /opt/gab-event
docker compose up -d
```

6. Ouvrez `https://votredomaine.com/`. Le cadenas du navigateur doit apparaître.

Renouvellement automatique (une fois par jour) :

```bash
crontab -e
```

Ajoutez :

```
0 3 * * * certbot renew --quiet && cd /opt/gab-event && docker compose exec -T gabevent-nginx nginx -s reload
```

---

## 6. Premier jour en production

- [ ] `DEBUG=False` dans `.env`
- [ ] `ALLOW_MOCK_PAYMENTS=False` si SingPay est branché
- [ ] Superutilisateur créé
- [ ] `https://votredomaine.com/health/` répond `ok`
- [ ] Connexion organisateur + création d’un événement test
- [ ] Scan d’un QR sur téléphone en HTTPS

---

## 7. Mettre à jour (livraison suivante)

Sur le VPS :

```bash
cd /opt/gab-event
git pull origin main
docker compose up -d --build
docker compose exec gabevent-web python manage.py migrate --noinput
docker compose exec gabevent-web python manage.py collectstatic --noinput
curl -fsS https://votredomaine.com/health/
```

Ou, depuis GitHub : **Actions → Déployer OVH → Run workflow**  
(après avoir ajouté les secrets `OVH_SSH_HOST`, `OVH_SSH_USER`, `OVH_SSH_KEY`).

---

## 8. Sauvegardes

Base Postgres :

```bash
docker compose exec -T gabevent-db pg_dump -U gabevent gabevent > /root/gabevent-$(date +%F).sql
```

Médias (flyers, logos) : le volume Docker `media_files`. Copiez-le régulièrement hors du VPS.

---

## 9. Problèmes fréquents

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| Page blanche, pas de CSS | `collectstatic` pas lancé | Relancer la commande ci-dessus |
| 400 CSRF | Mauvais `CSRF_TRUSTED_ORIGINS` | Doit commencer par `https://` + le domaine exact |
| DisallowedHost | `ALLOWED_HOSTS` incomplet | Ajouter le domaine, sans `https://` |
| 502 Bad Gateway | Django pas encore prêt | `docker compose ps` puis `docker compose logs gabevent-web` |
| Caméra scan bloquée | Site en HTTP | Activer le HTTPS |

Logs :

```bash
docker compose logs -f gabevent-web
```

---

## 10. Commandes utiles

```bash
docker compose ps
docker compose logs --tail=100 gabevent-web
docker compose restart gabevent-web
docker compose exec gabevent-web python manage.py check --deploy
```
