#!/usr/bin/env python3
"""
Génère les 3 guides Word de production Gab Event (design soigné).

Sortie :
  docs/guides/01_Guide_Utilisateur_Partenaires.docx
  docs/guides/02_Guide_Technique_Admin.docx
  docs/guides/03_Guide_Installation_Microservices_OVH.docx
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "guides"

# Palette Gab Event
NAVY = RGBColor(0x1A, 0x27, 0x44)
GOLD = RGBColor(0xC9, 0xA2, 0x4A)
GREEN = RGBColor(0x15, 0x99, 0x47)
MUTED = RGBColor(0x5C, 0x67, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CREAM = "FBF7F0"


def _set_cell_shading(cell, hex_color: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color)
    shading.set(qn("w:val"), "clear")
    cell._tePr = cell._tc.get_or_add_tcPr()
    cell._tc.get_or_add_tcPr().append(shading)


def _add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_begin)
    run._r.append(instr)
    run._r.append(fld_char_end)


def style_doc(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = NAVY
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

    for level, size in ((1, 22), (2, 16), (3, 13)):
        h = styles[f"Heading {level}"]
        h.font.name = "Calibri"
        h.font.bold = True
        h.font.size = Pt(size)
        h.font.color.rgb = NAVY if level > 1 else NAVY
        h.paragraph_format.space_before = Pt(16 if level == 1 else 12)
        h.paragraph_format.space_after = Pt(8)

    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Gab Event  ·  Confidentiel partenaires  ·  Page ")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    _add_page_number(p)

    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hr = hp.add_run("GAB EVENT")
    hr.bold = True
    hr.font.size = Pt(10)
    hr.font.color.rgb = GOLD
    hp.add_run("  —  Documentation officielle").font.size = Pt(9)
    hp.runs[-1].font.color.rgb = MUTED


def cover(doc: Document, eyebrow: str, title: str, subtitle: str, audience: str) -> None:
    # Bandeau couleur via tableau 1 cellule
    table = doc.add_table(rows=1, cols=1)
    table.autofit = True
    cell = table.cell(0, 0)
    _set_cell_shading(cell, "1A2744")
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("\nGAB EVENT\n")
    r.bold = True
    r.font.size = Pt(14)
    r.font.color.rgb = GOLD
    r2 = p.add_run(f"{eyebrow}\n")
    r2.font.size = Pt(11)
    r2.font.color.rgb = WHITE
    r3 = p.add_run(f"{title}\n")
    r3.bold = True
    r3.font.size = Pt(28)
    r3.font.color.rgb = WHITE
    r4 = p.add_run(f"{subtitle}\n\n")
    r4.font.size = Pt(12)
    r4.font.color.rgb = RGBColor(0xE8, 0xD6, 0xA8)

    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    m = meta.add_run(f"Public : {audience}\nVersion documentation — prêt production\n")
    m.font.size = Pt(11)
    m.font.color.rgb = MUTED
    doc.add_page_break()


def h(doc, text, level=1):
    doc.add_heading(text, level=level)


def p(doc, text):
    return doc.add_paragraph(text)


def bullets(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def numbered(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Number")


def callout(doc, title: str, body: str, color_hex: str = "ECFDF3") -> None:
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    _set_cell_shading(cell, color_hex)
    tp = cell.paragraphs[0]
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.color.rgb = NAVY
    tr.font.size = Pt(11)
    bp = cell.add_paragraph(body)
    for run in bp.runs:
        run.font.size = Pt(10)
        run.font.color.rgb = MUTED
    doc.add_paragraph()


def code_block(doc, text: str) -> None:
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    _set_cell_shading(cell, "F2F3F7")
    para = cell.paragraphs[0]
    run = para.add_run(text.strip("\n"))
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = NAVY
    doc.add_paragraph()


def simple_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        _set_cell_shading(cell, "1A2744")
        para = cell.paragraphs[0]
        run = para.add_run(header)
        run.bold = True
        run.font.color.rgb = WHITE
        run.font.size = Pt(10)
    for r_i, row in enumerate(rows):
        for c_i, value in enumerate(row):
            cell = table.rows[r_i + 1].cells[c_i]
            if r_i % 2 == 0:
                _set_cell_shading(cell, CREAM)
            para = cell.paragraphs[0]
            run = para.add_run(str(value))
            run.font.size = Pt(10)
            run.font.color.rgb = NAVY
    doc.add_paragraph()


def build_user_guide() -> Path:
    doc = Document()
    style_doc(doc)
    cover(
        doc,
        "FORMATIONATION PARTENAIRES",
        "Guide utilisateur",
        "Organiser invitations & billetterie sur Gab Event",
        "Organisateurs, partenaires commerciaux, équipes terrain",
    )

    h(doc, "1. À quoi sert Gab Event ?")
    p(
        doc,
        "Gab Event est une plateforme gabonaise pour créer et gérer des événements : "
        "invitations avec QR code, contrôle d’accès sur smartphone, et billetterie payante "
        "publique (concerts, galas, mariages, etc.).",
    )
    callout(
        doc,
        "Deux services distincts",
        "Espace Événements = invitations / cérémonies. "
        "Espace Billetterie = ventes de billets en ligne. "
        "Ne mélangez pas les deux parcours : chaque espace a sa propre navigation.",
        "FFF6E0",
    )

    h(doc, "2. Premiers pas")
    h(doc, "2.1 Créer un compte", 2)
    numbered(
        doc,
        [
            "Ouvrez le site public Gab Event.",
            "Cliquez sur Connexion puis Créer un compte (ou le CTA de la page d’accueil).",
            "Renseignez un identifiant, un e-mail valide et un mot de passe solide.",
            "Connectez-vous : vous arrivez sur « Vos événements ».",
        ],
    )
    h(doc, "2.2 Compléter le profil (obligatoire pour être payé)", 2)
    bullets(
        doc,
        [
            "Menu → Profil : photo, nom affiché, coordonnées.",
            "Mobile Money : numéro confirmé — indispensable pour les reversements billetterie.",
            "Sans Mobile Money confirmé, la publication payante peut être bloquée en production.",
        ],
    )

    h(doc, "3. Espace Événements (invitations)")
    h(doc, "3.1 Créer un événement", 2)
    numbered(
        doc,
        [
            "Barre du bas → Créer (ou bouton Créer sur desktop).",
            "Choisissez le type (cérémonie, mariage, gala…).",
            "Renseignez nom, date, lieu, organisateur.",
            "Choisissez une formule (gratuit ou payante selon les quotas).",
            "Personnalisez le style (couleurs, affiche, logo) dans Style.",
        ],
    )
    h(doc, "3.2 Inviter et scanner", 2)
    bullets(
        doc,
        [
            "Invités : ajoutez manuellement ou via le lien d’invitation.",
            "Cartes : téléchargez les cartes PNG / ZIP avec QR.",
            "Contrôle : page scan pour valider l’entrée (places consommées).",
            "Présence : suivi des présents en temps réel.",
        ],
    )
    simple_table(
        doc,
        ["Écran", "Rôle"],
        [
            ["Aperçu", "Tableau de bord de l’événement"],
            ["Invités", "Liste et fiches"],
            ["Lien", "Lien public d’inscription / invitation"],
            ["Cartes", "Visuels QR à imprimer ou envoyer"],
            ["Contrôle", "Scan d’entrée"],
            ["Présence", "Statistiques de présence"],
        ],
    )

    h(doc, "4. Espace Billetterie (ventes)")
    p(
        doc,
        "Accès : bouton vert Billetterie (menu, navigation desktop) ou icône ticket "
        "en haut à droite sur mobile depuis l’espace organisateur.",
    )
    h(doc, "4.1 Créer une vente", 2)
    numbered(
        doc,
        [
            "Billetterie → Nouvel événement (ou Créer dans la barre billetterie).",
            "Ajoutez une affiche (JPG/PNG) — visible sur l’agenda et le billet.",
            "Renseignez nom, organisé par, catégorie, description, lieu, date/heure.",
            "Définissez au moins un tarif (ex. Standard, VIP) avec prix en F CFA.",
            "Enregistrez, puis publiez depuis le tableau de bord pour apparaître sur l’agenda public.",
        ],
    )
    h(doc, "4.2 Suivre les ventes", 2)
    bullets(
        doc,
        [
            "Carte hub : billets vendus + montant total collecté (pas le prix de départ).",
            "Dashboard : onglets Publication, Tarifs, Ventes.",
            "Copiez le lien d’achat pour le partager (WhatsApp, réseaux).",
            "« Simuler un achat » n’apparaît qu’en environnement de test — jamais en production réelle.",
        ],
    )
    h(doc, "4.3 Agenda public & ticket perdu", 2)
    bullets(
        doc,
        [
            "Agenda : le public voit les événements « du moment » / à venir.",
            "Fiche événement : countdown, infos, Acheter un billet (vert), Récupérer mon ticket perdu.",
            "Le couple de boutons reste visible en bas de la fiche (bottom sheet).",
        ],
    )

    h(doc, "5. Bonnes pratiques terrain")
    bullets(
        doc,
        [
            "Testez toujours un parcours complet (création → publication → achat test en sandbox).",
            "Vérifiez l’affiche et les tarifs avant publication.",
            "Formez les contrôleurs d’accès avec un compte / session dédiée si besoin.",
            "Ne partagez jamais vos identifiants admin ou superutilisateur.",
            "En cas de panne réseau, les pages déjà ouvertes peuvent rester utilisables (PWA).",
        ],
    )

    h(doc, "6. Aide rapide")
    simple_table(
        doc,
        ["Problème", "Que faire"],
        [
            ["Je ne vois pas mes ventes dans « Vos événements »", "Normal : elles sont uniquement dans Billetterie."],
            ["Publication refusée", "Confirmez Mobile Money + tarifs + affiche."],
            ["QR illisible", "Régénérez la carte ; imprimez en bonne qualité."],
            ["Paiement bloqué", "Vérifiez SingPay / sandbox avec l’admin plateforme."],
            ["Mot de passe oublié", "Utilisez « Mot de passe oublié » (e-mail ou OTP selon config)."],
        ],
    )
    callout(
        doc,
        "Support",
        "Contactez l’administrateur de la plateforme Gab Event pour toute demande "
        "d’accès partenaire, de formule ou de reversement.",
        "ECFDF3",
    )

    path = OUT / "01_Guide_Utilisateur_Partenaires.docx"
    doc.save(path)
    return path


def build_admin_guide() -> Path:
    doc = Document()
    style_doc(doc)
    cover(
        doc,
        "ADMINISTRATION PLATEFORME",
        "Guide technique admin",
        "Installation, maintenance et exploitation quotidienne",
        "Administrateurs système & opérateurs plateforme",
    )

    h(doc, "1. Rôles et accès")
    simple_table(
        doc,
        ["Rôle", "Accès"],
        [
            ["Organisateur", "Espace événements + billetterie de ses propres ventes"],
            ["Staff Django", "/admin/ (modèles, utilisateurs)"],
            ["Platform admin", "/platform-admin/ (console métier : users, paiements, CMS)"],
            ["Superuser", "Tous les droits"],
        ],
    )
    callout(
        doc,
        "Sécurité",
        "En production : DEBUG=False, ALLOW_MOCK_PAYMENTS=False, SECRET_KEY unique, "
        "HTTPS obligatoire, superuser réservé à 1–2 personnes de confiance.",
        "FEE2E2",
    )

    h(doc, "2. Installation locale (admin développeur)")
    code_block(
        doc,
        """cd Gab-Event
python -m venv venv
# Windows: .\\venv\\Scripts\\Activate.ps1
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # ou cp .env.example .env
# Éditer SECRET_KEY, DEBUG=True pour le local uniquement
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver""",
    )

    h(doc, "3. Console platform-admin")
    bullets(
        doc,
        [
            "Utilisateurs : activation, quotas, recherche.",
            "Événements : statut, archivage, vue propriétaire.",
            "Paiements / Billetterie : ledger, commissions, reversements.",
            "Config site : logo, textes landing, commission_pct, allow_mock_payments.",
            "FAQ, catégories, formules (plans).",
        ],
    )
    p(
        doc,
        "La case « paiements mock » ne doit rester cochée qu’en DEBUG. "
        "Dès que SingPay est branché, décochez-la.",
    )

    h(doc, "4. Paiements & SingPay")
    simple_table(
        doc,
        ["Variable", "Rôle"],
        [
            ["PAYMENT_PROVIDER", "mock | singpay"],
            ["SINGPAY_API_KEY / SECRET / MERCHANT_ID", "Identifiants marchand"],
            ["SINGPAY_ENVIRONMENT", "sandbox ou live"],
            ["PUBLIC_BASE_URL", "URL publique pour callbacks"],
            ["ALLOW_MOCK_PAYMENTS", "False en production"],
        ],
    )
    h(doc, "4.1 Checklist avant go-live paiement", 2)
    numbered(
        doc,
        [
            "Clés SingPay live validées.",
            "PUBLIC_BASE_URL = https://votre-domaine",
            "Webhook / return URLs accessibles en HTTPS.",
            "ALLOW_MOCK_PAYMENTS=False et DEBUG=False.",
            "Tester un achat réel à faible montant puis remboursement selon procédure SingPay.",
            "Vérifier commission_pct dans SiteSettings.",
        ],
    )

    h(doc, "5. Maintenance courante")
    h(doc, "5.1 Mises à jour code", 2)
    code_block(
        doc,
        """git pull --ff-only origin main
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# Redémarrer le process WSGI / conteneurs selon l’hébergeur""",
    )
    h(doc, "5.2 Sauvegardes", 2)
    bullets(
        doc,
        [
            "Base Postgres : pg_dump quotidien + rétention 7–30 jours.",
            "Médias (affiches, avatars) : volume / dossier media synchronisé.",
            "Fichier .env : stocké hors dépôt, sauvegarde chiffrée.",
        ],
    )
    h(doc, "5.3 Journaux & santé", 2)
    bullets(
        doc,
        [
            "Endpoint /health/ doit répondre status ok.",
            "Surveiller erreurs 5xx nginx / gunicorn.",
            "Celery worker + beat : files d’attente Redis non saturées.",
        ],
    )

    h(doc, "6. Exploitation métier")
    bullets(
        doc,
        [
            "Archivage automatique selon lifetime_days / expires_at des événements.",
            "Invitations annulées (statut desactive = « Annulée »).",
            "Reversements Mobile Money : profil organisateur prêt (momo_ready).",
            "Ne jamais supprimer un organisateur actif sans traitement des paiements ouverts.",
        ],
    )

    h(doc, "7. Incidents fréquents")
    simple_table(
        doc,
        ["Symptôme", "Cause probable", "Action"],
        [
            ["OperationalError colonne manquante", "Migration non appliquée", "migrate --noinput"],
            ["DisallowedHost", "ALLOWED_HOSTS incomplet", "Ajouter le domaine"],
            ["CSRF failed", "CSRF_TRUSTED_ORIGINS", "Ajouter https://domaine"],
            ["Static 404", "collectstatic / WhiteNoise / nginx", "Rebuild static volume"],
            ["Mock encore visible", "DEBUG ou allow_mock", "Couper DEBUG et mock"],
        ],
    )

    h(doc, "8. Tests avant mise en prod")
    code_block(
        doc,
        """python manage.py check --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py makemigrations --check --dry-run""",
    )

    path = OUT / "02_Guide_Technique_Admin.docx"
    doc.save(path)
    return path


def build_install_guide() -> Path:
    doc = Document()
    style_doc(doc)
    cover(
        doc,
        "DEVOPS · GITHUB ACTIONS · OVH CLOUD",
        "Guide d’installation complet",
        "Déploiement microservices sur VPS (Docker Compose + CI/CD)",
        "Ingénieurs DevOps, administrateurs système",
    )

    h(doc, "1. Architecture cible (microservices applicatifs)")
    p(
        doc,
        "Gab Event se déploie comme un ensemble de services Docker orchestrés par Compose. "
        "Ce n’est pas un monolithe « tout-en-un » opaque : chaque conteneur a un rôle clair.",
    )
    simple_table(
        doc,
        ["Service", "Image / build", "Rôle"],
        [
            ["gabevent-db", "postgres:16-alpine", "Données relationnelles"],
            ["gabevent-redis", "redis:7-alpine", "Broker Celery + cache"],
            ["gabevent-web", "Dockerfile (Django/Gunicorn)", "API HTTP + app"],
            ["gabevent-celery-worker", "même image", "Tâches asynchrones"],
            ["gabevent-celery-beat", "même image", "Planification"],
            ["gabevent-nginx", "nginx:1.25-alpine", "Reverse proxy, static, TLS"],
        ],
    )
    callout(
        doc,
        "Principe",
        "Le trafic Internet arrive sur nginx (80/443). Nginx proxy vers gabevent-web:8000. "
        "Web, worker et beat partagent le même code mais des commandes différentes.",
        "ECFDF3",
    )

    h(doc, "2. Prérequis")
    bullets(
        doc,
        [
            "VPS OVH Cloud Ubuntu 24.04, ≥ 2 Go RAM (4 Go recommandé avec Celery).",
            "Domaine avec enregistrements DNS A vers l’IP du VPS.",
            "Compte GitHub avec accès au dépôt et droits secrets Actions.",
            "Accès SSH clé privée (pas de mot de passe root en production).",
        ],
    )

    h(doc, "3. Préparation du VPS (commandes)")
    code_block(
        doc,
        """ssh root@ADRESSE_IP_DU_VPS

apt-get update
apt-get install -y git curl ufw
curl -fsSL https://raw.githubusercontent.com/Stevy64/Gab-Event/main/deploy/ovh-setup.sh | bash

# Pare-feu minimal
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable""",
    )

    h(doc, "4. Installation de l’application")
    code_block(
        doc,
        """git clone https://github.com/Stevy64/Gab-Event.git /opt/gab-event
cd /opt/gab-event
cp deploy/ovh.env.example .env
nano .env""",
    )
    p(doc, "Variables obligatoires dans .env :")
    simple_table(
        doc,
        ["Variable", "Exemple / règle"],
        [
            ["SECRET_KEY", "python3 -c \"import secrets; print(secrets.token_urlsafe(50))\""],
            ["DEBUG", "False"],
            ["ALLOW_MOCK_PAYMENTS", "False"],
            ["ALLOWED_HOSTS", "domaine.com,www.domaine.com"],
            ["CSRF_TRUSTED_ORIGINS", "https://domaine.com,https://www.domaine.com"],
            ["PUBLIC_BASE_URL", "https://domaine.com"],
            ["POSTGRES_PASSWORD", "Mot de passe long unique"],
            ["PAYMENT_PROVIDER", "singpay (si clés présentes)"],
        ],
    )
    code_block(
        doc,
        """cd /opt/gab-event
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1/health/
docker compose exec -T gabevent-web python manage.py createsuperuser""",
    )

    h(doc, "5. HTTPS (Let’s Encrypt)")
    code_block(
        doc,
        """apt-get install -y certbot
# Option standalone (arrêt temporaire nginx)
docker compose stop gabevent-nginx
certbot certonly --standalone -d votredomaine.com -d www.votredomaine.com
docker compose start gabevent-nginx

cp nginx/conf.d/gabevent-ssl.conf.example nginx/conf.d/gabevent-ssl.conf
# Remplacer VOTRE_DOMAINE dans gabevent-ssl.conf
mv nginx/conf.d/gabevent.conf nginx/conf.d/gabevent.conf.off

# Dans docker-compose.yml : exposer 443 + monter /etc/letsencrypt
docker compose up -d

# Renouvellement
crontab -e
# 0 3 * * * certbot renew --quiet && cd /opt/gab-event && docker compose exec -T gabevent-nginx nginx -s reload""",
    )

    h(doc, "6. GitHub Actions — déploiement continu")
    p(
        doc,
        "Le workflow `.github/workflows/deploy-ovh.yml` se lance manuellement "
        "(workflow_dispatch) ou peut être branché sur push main après validation CI.",
    )
    h(doc, "6.1 Secrets GitHub à créer", 2)
    simple_table(
        doc,
        ["Secret", "Contenu"],
        [
            ["OVH_SSH_HOST", "IP ou hostname du VPS"],
            ["OVH_SSH_USER", "root ou utilisateur deploy"],
            ["OVH_SSH_KEY", "Clé privée SSH (PEM) sans passphrase idéalement via agent"],
        ],
    )
    h(doc, "6.2 Déroulement du job", 2)
    numbered(
        doc,
        [
            "Vérifie la présence des secrets.",
            "SSH sur le VPS.",
            "git fetch + pull --ff-only origin main dans /opt/gab-event.",
            "docker compose up -d --build.",
            "migrate --noinput + collectstatic --noinput.",
            "curl healthcheck local.",
        ],
    )
    h(doc, "6.3 CI préalable (.github/workflows/ci.yml)", 2)
    bullets(
        doc,
        [
            "check Django (test_settings).",
            "tests SQLite.",
            "tests Postgres service.",
            "Ne déployez en production que si CI est verte.",
        ],
    )
    callout(
        doc,
        "Conseil production",
        "Ajoutez une règle : deploy-ovh uniquement après succès du workflow CI sur le même commit. "
        "Évitez de pousser DEBUG=True ou des secrets dans le dépôt.",
        "FFF6E0",
    )

    h(doc, "7. Commandes d’exploitation quotidiennes")
    code_block(
        doc,
        """cd /opt/gab-event

# Statut
docker compose ps
docker compose logs -f --tail=200 gabevent-web

# Mise à jour manuelle
git pull --ff-only origin main
docker compose up -d --build
docker compose exec -T gabevent-web python manage.py migrate --noinput
docker compose exec -T gabevent-web python manage.py collectstatic --noinput

# Shell Django
docker compose exec gabevent-web python manage.py shell

# Sauvegarde Postgres
docker compose exec -T gabevent-db pg_dump -U gabevent gabevent > backup_$(date +%F).sql""",
    )

    h(doc, "8. Checklist go-live")
    numbered(
        doc,
        [
            "DNS OK (ping domaine = IP VPS).",
            "HTTPS cadenas OK.",
            "DEBUG=False, ALLOW_MOCK_PAYMENTS=False.",
            "createsuperuser effectué, mot de passe stocké en coffre.",
            "SingPay live testé.",
            "Sauvegarde automatique planifiée.",
            "Monitoring /health/ (UptimeRobot ou équivalent).",
            "Workflow Actions testé une fois à la main.",
        ],
    )

    h(doc, "9. Rollback rapide")
    code_block(
        doc,
        """cd /opt/gab-event
git log --oneline -5
git checkout COMMIT_STABLE
docker compose up -d --build
docker compose exec -T gabevent-web python manage.py migrate --noinput
# Si migration destructive : restaurer le dump SQL avant migrate""",
    )

    path = OUT / "03_Guide_Installation_Microservices_OVH.docx"
    doc.save(path)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [build_user_guide(), build_admin_guide(), build_install_guide()]
    readme = OUT / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Guides Word — Gab Event",
                "",
                "Documents générés par `python scripts/build_prod_guides.py`.",
                "",
                "| Fichier | Usage |",
                "|---------|--------|",
                "| `01_Guide_Utilisateur_Partenaires.docx` | Formation organisateurs / partenaires |",
                "| `02_Guide_Technique_Admin.docx` | Admin plateforme, maintenance, SingPay |",
                "| `03_Guide_Installation_Microservices_OVH.docx` | DevOps Docker + GitHub Actions + OVH |",
                "",
                "Design : charte Gab Event (navy / or / vert), pages de couverture, tableaux, encadrés.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    for path in paths:
        print(f"OK {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
