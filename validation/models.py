"""
Modèles métier — plateforme multi-événements Gab Event.

Hiérarchie :
  User → EventPlan / Event → Invitation → ScanLog / Admission
  Payment, UserProfile, AdminAuditLog, EventLimitAdjustment
"""
from __future__ import annotations

import re
import string
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .branding import (
    DEFAULT_PRIMARY_COLOR,
    default_logo_url,
    display_color,
    year_code_prefix,
)
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP


# ---------------------------------------------------------------------------
# Plans & utilisateurs
# ---------------------------------------------------------------------------


class EventPlan(models.Model):
    """Formule commerciale administrable (limites & prix en base)."""

    name = models.CharField("Nom", max_length=120)
    slug = models.SlugField(unique=True, max_length=80)
    description = models.TextField("Description", blank=True, default="")
    regular_invitation_limit = models.PositiveIntegerField(
        "Limite invitations standard",
        default=30,
    )
    vip_invitation_limit = models.PositiveIntegerField(
        "Limite invitations VIP",
        default=0,
    )
    # Offre gratuite : capacité globale (standard + VIP) si > 0
    total_invitation_limit = models.PositiveIntegerField(
        "Limite totale (0 = non utilisée)",
        default=0,
        help_text="Si > 0, plafonne le total standard+VIP (ex. offre gratuite 30).",
    )
    price = models.DecimalField(
        "Prix",
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    currency = models.CharField("Devise", max_length=8, default="XOF")
    is_free = models.BooleanField("Gratuit", default=False)
    is_custom = models.BooleanField(
        "Formule à la carte",
        default=False,
        help_text="Tarif à l'invitation, sans quota fixe.",
    )
    lifetime_days = models.PositiveIntegerField(
        "Durée de vie (jours)",
        null=True,
        blank=True,
        help_text="Archivage automatique N jours après la date de l’événement (J+N). Vide pour une fenêtre définie à la création (Personnalisé).",
    )
    price_per_regular = models.DecimalField(
        "Prix / invitation standard",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    price_per_vip = models.DecimalField(
        "Prix / invitation VIP",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    extra_ticket_price = models.DecimalField(
        "Prix / billet supplémentaire",
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Tarif d’un billet au-delà du forfait inclus. 0 = non proposé.",
    )
    is_active = models.BooleanField("Actif", default=True)
    is_recommended = models.BooleanField("Recommandé", default=False)
    display_order = models.PositiveIntegerField("Ordre d'affichage", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "price", "name"]
        verbose_name = "Formule"
        verbose_name_plural = "Formules"

    def __str__(self):
        return self.name

    @property
    def is_popular(self) -> bool:
        return self.slug == "petit"

    @property
    def potential_total(self) -> int:
        if self.total_invitation_limit:
            return self.total_invitation_limit
        return self.regular_invitation_limit + self.vip_invitation_limit

    def covers_guest_count(self, expected: int) -> bool:
        if self.is_custom:
            return True
        return self.potential_total >= int(expected or 0)

    @property
    def lifetime_label(self) -> str:
        if self.is_custom or not self.lifetime_days:
            return "Fenêtre de validité définie à la création"
        n = int(self.lifetime_days)
        return f"Accessible jusqu’à J+{n}"

    @property
    def capacity_label(self) -> str:
        if self.is_custom:
            return ""
        if self.total_invitation_limit:
            return f"Jusqu’à {self.total_invitation_limit} personnes"
        parts = []
        if self.regular_invitation_limit:
            noun = "standard" if self.regular_invitation_limit == 1 else "standards"
            parts.append(f"{self.regular_invitation_limit} {noun}")
        if self.vip_invitation_limit:
            parts.append(f"{self.vip_invitation_limit} VIP")
        return " + ".join(parts)

    @property
    def extra_ticket_label(self) -> str:
        if self.is_custom:
            return ""
        try:
            amount = int(self.extra_ticket_price or 0)
        except (TypeError, ValueError):
            return ""
        if amount <= 0:
            return ""
        return f"{amount} F CFA par billet supplémentaire"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField("Nom affiché", max_length=160, blank=True, default="")
    organization_name = models.CharField(
        "Organisation",
        max_length=160,
        blank=True,
        default="",
    )
    phone = models.CharField("Téléphone", max_length=40, blank=True, default="")
    MOMO_AIRTEL = "airtel"
    MOMO_MOOV = "moov"
    MOMO_CHOICES = [
        (MOMO_AIRTEL, "Airtel Money"),
        (MOMO_MOOV, "Moov Money"),
    ]
    momo_operator = models.CharField(
        "Opérateur Mobile Money",
        max_length=16,
        choices=MOMO_CHOICES,
        blank=True,
        default="",
    )
    momo_phone = models.CharField(
        "Numéro Mobile Money",
        max_length=40,
        blank=True,
        default="",
    )
    momo_confirmed_at = models.DateTimeField(
        "Mobile Money confirmé le",
        null=True,
        blank=True,
    )
    avatar = models.ImageField(
        "Avatar",
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(phone=""),
                name="unique_profile_phone_nonempty",
            )
        ]

    def __str__(self):
        return self.display_name or self.user.get_username()

    @property
    def momo_ready(self) -> bool:
        return bool(self.momo_operator and self.momo_phone and self.momo_confirmed_at)

    @property
    def momo_label(self) -> str:
        if not self.momo_phone:
            return "Non renseigné"
        op = self.get_momo_operator_display() if self.momo_operator else "Mobile Money"
        return f"{op} · {self.momo_phone}"


class RecoveryOtp(models.Model):
    """Code à usage unique pour récupérer un compte par téléphone."""

    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_SMS = "sms"
    CHANNEL_CONSOLE = "console"
    CHANNEL_CHOICES = (
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_CONSOLE, "Console / test"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recovery_otps",
    )
    phone = models.CharField("Téléphone", max_length=40)
    code_hash = models.CharField(max_length=64)
    channel = models.CharField(
        max_length=16,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_CONSOLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Code de récupération"
        verbose_name_plural = "Codes de récupération"
        indexes = [
            models.Index(
                fields=["user", "consumed_at"],
                name="validation__user_id_recov_idx",
            ),
        ]

    def __str__(self):
        return f"OTP {self.user_id} {self.phone}"


# ---------------------------------------------------------------------------
# Événements
# ---------------------------------------------------------------------------


def _default_code_prefix() -> str:
    return year_code_prefix()


class Event(models.Model):
    """Événement appartenant à un utilisateur (isolation multi-tenant)."""

    TYPE_CEREMONY = "ceremony"
    TYPE_WEDDING = "wedding"
    TYPE_GRADUATION = "graduation"
    TYPE_CONFERENCE = "conference"
    TYPE_GALA = "gala"
    TYPE_CONCERT = "concert"
    TYPE_BIRTHDAY = "birthday"
    TYPE_RECEPTION = "reception"
    TYPE_PROFESSIONAL = "professional"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_CEREMONY, "Cérémonie"),
        (TYPE_WEDDING, "Mariage"),
        (TYPE_GRADUATION, "Remise de diplômes"),
        (TYPE_CONFERENCE, "Conférence"),
        (TYPE_GALA, "Gala"),
        (TYPE_CONCERT, "Concert"),
        (TYPE_BIRTHDAY, "Anniversaire"),
        (TYPE_RECEPTION, "Réception"),
        (TYPE_PROFESSIONAL, "Événement professionnel"),
        (TYPE_OTHER, "Autre"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"
    STATUS_COMPLETED = "completed"
    STATUS_ARCHIVED = "archived"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PENDING_PAYMENT, "En attente de paiement"),
        (STATUS_ACTIVE, "Actif"),
        (STATUS_DISABLED, "Désactivé"),
        (STATUS_COMPLETED, "Terminé"),
        (STATUS_ARCHIVED, "Archivé"),
        (STATUS_CANCELLED, "Annulé"),
    ]
    GRAND_PLAN_SLUG = "grand"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
    )
    plan = models.ForeignKey(
        EventPlan,
        on_delete=models.PROTECT,
        related_name="events",
        null=True,
        blank=True,
    )
    name = models.CharField("Nom", max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    event_type = models.CharField(
        "Type",
        max_length=40,
        choices=TYPE_CHOICES,
        default=TYPE_OTHER,
    )
    event_type_custom = models.CharField(
        "Type personnalisé",
        max_length=80,
        blank=True,
        default="",
        help_text="Ex. Noël, Nouvel an, Baptême…",
    )
    description = models.TextField("Description", blank=True, default="")
    date = models.DateField("Date", null=True, blank=True)
    start_time = models.TimeField("Heure de début", null=True, blank=True)
    end_time = models.TimeField("Heure de fin", null=True, blank=True)
    venue = models.CharField("Lieu", max_length=200, blank=True, default="")
    address = models.CharField("Adresse", max_length=255, blank=True, default="")
    city = models.CharField("Ville", max_length=120, blank=True, default="")
    organizer_name = models.CharField(
        "Organisateur",
        max_length=160,
        blank=True,
        default="",
    )
    contact_information = models.CharField(
        "Contact",
        max_length=255,
        blank=True,
        default="",
    )
    flyer = models.ImageField(
        "Flyer",
        upload_to="flyers/%Y/%m/",
        blank=True,
        null=True,
    )
    logo = models.ImageField(
        "Logo",
        upload_to="logos/%Y/%m/",
        blank=True,
        null=True,
    )
    show_on_homepage = models.BooleanField(
        "Afficher sur la page d'accueil",
        default=False,
        help_text="Si activé et qu'un flyer est présent, l'événement apparaît dans le carrousel public.",
    )
    is_public = models.BooleanField(
        "Événement public",
        default=False,
        help_text="Affiché sur la page Événements publics (indépendamment du carrousel).",
    )
    is_ticketing = models.BooleanField(
        "Billetterie",
        default=False,
        help_text="Événement vendu via la billetterie (concerts, festivals, etc.).",
    )
    invite_access_code = models.CharField(
        "Code de validation du lien",
        max_length=40,
        blank=True,
        default="",
        help_text="Optionnel. Les invités doivent le saisir pour ouvrir le formulaire.",
    )
    animated_card = models.BooleanField(
        "Carte d'invitation animée",
        default=False,
        help_text="Option prestige : animation, musique et nom de l'invité (quelques secondes).",
    )
    primary_color = models.CharField(
        "Couleur principale",
        max_length=16,
        blank=True,
        default=DEFAULT_PRIMARY_COLOR,
    )
    welcome_text = models.TextField("Texte d'accueil", blank=True, default="")
    invitation_message = models.TextField(
        "Message d'invitation",
        blank=True,
        default="",
    )
    status = models.CharField(
        "Statut",
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    code_prefix = models.CharField(
        "Préfixe QR",
        max_length=24,
        unique=True,
        help_text="Préfixe des codes d'invitation (ex. GAE26).",
    )
    # Snapshot commercial au moment de l'activation / paiement
    plan_name_snapshot = models.CharField(max_length=120, blank=True, default="")
    regular_limit_snapshot = models.PositiveIntegerField(null=True, blank=True)
    vip_limit_snapshot = models.PositiveIntegerField(null=True, blank=True)
    total_limit_snapshot = models.PositiveIntegerField(null=True, blank=True)
    price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency_snapshot = models.CharField(max_length=8, blank=True, default="")
    # Ajustements admin optionnels (écrasent le snapshot si renseignés)
    custom_regular_limit = models.PositiveIntegerField(null=True, blank=True)
    custom_vip_limit = models.PositiveIntegerField(null=True, blank=True)
    custom_total_limit = models.PositiveIntegerField(null=True, blank=True)
    is_legacy = models.BooleanField(
        "Événement historique migré",
        default=False,
        help_text="Conserve la compatibilité ATC24 / VIP existants.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField("Archivé le", null=True, blank=True)
    delete_prompt_dismissed_at = models.DateTimeField(
        "Proposition de suppression refusée le",
        null=True,
        blank=True,
    )
    invite_token = models.CharField(
        "Jeton lien d’invitation",
        max_length=40,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
    )
    invite_form_fields = models.JSONField(
        "Champs du formulaire invité",
        default=list,
        blank=True,
    )
    invite_published_at = models.DateTimeField(
        "Formulaire mis en ligne le",
        null=True,
        blank=True,
    )
    invite_link_enabled = models.BooleanField(
        "Lien d’invitation actif",
        default=False,
    )
    guest_price_regular = models.DecimalField(
        "Tarif invité standard",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    guest_price_vip = models.DecimalField(
        "Tarif invité VIP",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    validity_starts_on = models.DateField(
        "Début de validité",
        null=True,
        blank=True,
    )
    validity_ends_on = models.DateField(
        "Fin de validité",
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField(
        "Archivage automatique le",
        null=True,
        blank=True,
        db_index=True,
    )
    invite_valid_from = models.DateField(
        "Lien invité — début",
        null=True,
        blank=True,
    )
    invite_valid_until = models.DateField(
        "Lien invité — fin",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Événement"
        verbose_name_plural = "Événements"
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["status", "date"]),
        ]

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_date = self.date

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        prev_date = getattr(self, "_original_date", self.date)
        if not self.slug:
            base = slugify(self.name)[:180] or "evenement"
            candidate = base
            n = 1
            while Event.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                n += 1
                candidate = f"{base}-{n}"
            self.slug = candidate
        if not self.code_prefix:
            base = year_code_prefix()
            candidate = base
            n = 0
            letters = string.ascii_uppercase
            while Event.objects.filter(code_prefix__iexact=candidate).exclude(pk=self.pk).exists():
                n += 1
                if n <= 26:
                    candidate = f"{base}{letters[n - 1]}"
                else:
                    candidate = f"{base}{n}"
            self.code_prefix = candidate
        else:
            self.code_prefix = self.code_prefix.upper().strip()
        if not self.primary_color:
            self.primary_color = DEFAULT_PRIMARY_COLOR
        super().save(*args, **kwargs)
        if self.pk and self.plan_id and not self.is_legacy:
            catalog = not (self.plan and self.plan.is_custom)
            refresh = (not self.expires_at) or is_new
            if not refresh and catalog and prev_date != self.date:
                refresh = True
            if refresh:
                self.apply_lifetime()
                super().save(
                    update_fields=[
                        "validity_starts_on",
                        "validity_ends_on",
                        "expires_at",
                        "invite_valid_from",
                        "invite_valid_until",
                        "updated_at",
                    ]
                )
        self._original_date = self.date

    def apply_plan_snapshot(self, plan: EventPlan | None = None) -> None:
        plan = plan or self.plan
        if not plan:
            return
        self.plan = plan
        self.plan_name_snapshot = plan.name
        self.regular_limit_snapshot = plan.regular_invitation_limit
        self.vip_limit_snapshot = plan.vip_invitation_limit
        self.total_limit_snapshot = plan.total_invitation_limit or None
        self.price_snapshot = plan.price
        self.currency_snapshot = plan.currency
        if not self.expires_at:
            self.apply_lifetime()

    LIFETIME_BY_SLUG = {
        "gratuit": 14,
        "petit": 21,
        "moyen": 30,
        "grand": 60,
    }

    def apply_lifetime(self, *, starts=None, ends=None) -> None:
        """Accessible dès la création, jusqu’à J+N après la date de l’événement."""
        if starts:
            self.validity_starts_on = starts
        if ends:
            self.validity_ends_on = ends
        created = self.created_at or timezone.now()
        if timezone.is_aware(created):
            created_day = timezone.localtime(created).date()
        else:
            created_day = created.date()
        plan = self.plan if self.plan_id else None
        event_day = self.date or created_day
        if plan and plan.is_custom:
            if not self.validity_starts_on:
                self.validity_starts_on = created_day
            if not self.validity_ends_on:
                self.validity_ends_on = event_day + timedelta(days=30)
            end_dt = datetime.combine(self.validity_ends_on, time(23, 59, 59))
            self.expires_at = timezone.make_aware(end_dt, timezone.get_current_timezone())
        else:
            days = None
            if plan and plan.lifetime_days:
                days = int(plan.lifetime_days)
            elif plan:
                days = self.LIFETIME_BY_SLUG.get(plan.slug)
            days = days or 14
            self.validity_starts_on = created_day
            self.validity_ends_on = event_day + timedelta(days=days)
            end_dt = datetime.combine(self.validity_ends_on, time(23, 59, 59))
            self.expires_at = timezone.make_aware(end_dt, timezone.get_current_timezone())
        self.apply_default_invite_window()

    def apply_default_invite_window(self) -> None:
        start = self.validity_starts_on or timezone.localdate()
        end = self.validity_ends_on
        if not self.invite_valid_from:
            self.invite_valid_from = start
        if not self.invite_valid_until and end:
            self.invite_valid_until = end
        if self.validity_starts_on and self.invite_valid_from:
            if self.invite_valid_from < self.validity_starts_on:
                self.invite_valid_from = self.validity_starts_on
        if self.validity_ends_on and self.invite_valid_until:
            if self.invite_valid_until > self.validity_ends_on:
                self.invite_valid_until = self.validity_ends_on

    def set_invite_window(self, starts, ends) -> None:
        self.invite_valid_from = starts
        self.invite_valid_until = ends
        self.apply_default_invite_window()

    @property
    def days_until_expiry(self):
        if not self.expires_at:
            return None
        return (timezone.localtime(self.expires_at).date() - timezone.localdate()).days

    @property
    def invite_window_state(self) -> str:
        if not self.invite_link_enabled:
            return "disabled"
        today = timezone.localdate()
        if self.expires_at and timezone.now() >= self.expires_at:
            return "ended"
        if self.invite_valid_from and today < self.invite_valid_from:
            return "upcoming"
        if self.invite_valid_until and today > self.invite_valid_until:
            return "ended"
        return "open"

    @property
    def invite_window_open(self) -> bool:
        return self.invite_window_state == "open"

    @property
    def regular_limit(self) -> int:
        if self.custom_regular_limit is not None:
            return self.custom_regular_limit
        if self.regular_limit_snapshot is not None:
            return self.regular_limit_snapshot
        if self.plan_id:
            return self.plan.regular_invitation_limit
        return 0

    @property
    def vip_limit(self) -> int:
        if self.custom_vip_limit is not None:
            return self.custom_vip_limit
        if self.vip_limit_snapshot is not None:
            return self.vip_limit_snapshot
        if self.plan_id:
            return self.plan.vip_invitation_limit
        return 0

    @property
    def total_limit(self) -> int | None:
        if self.custom_total_limit is not None:
            return self.custom_total_limit
        if self.total_limit_snapshot is not None:
            return self.total_limit_snapshot
        if self.plan_id and self.plan.total_invitation_limit:
            return self.plan.total_invitation_limit
        return None

    @property
    def is_active_event(self) -> bool:
        return self.status == self.STATUS_ACTIVE

    @property
    def is_disabled(self) -> bool:
        return self.status in {self.STATUS_DISABLED, self.STATUS_CANCELLED}

    @property
    def is_within_validity(self) -> bool:
        now = timezone.now()
        today = timezone.localdate()
        if self.expires_at and now >= self.expires_at:
            return False
        if self.validity_ends_on and today > self.validity_ends_on:
            return False
        if self.validity_starts_on and today < self.validity_starts_on:
            return False
        return True

    @property
    def is_happening_now(self) -> bool:
        """Jour J (et horaires si renseignés) : l’événement est en cours."""
        if self.status != self.STATUS_ACTIVE or not self.date:
            return False
        today = timezone.localdate()
        if self.date != today:
            return False
        now_t = timezone.localtime().time()
        if self.start_time and self.end_time:
            if self.end_time < self.start_time:
                return now_t >= self.start_time or now_t <= self.end_time
            return self.start_time <= now_t <= self.end_time
        if self.start_time:
            return now_t >= self.start_time
        return True

    def lifecycle_actions(self) -> dict:
        from .event_lifecycle import available_actions

        return available_actions(self)

    @property
    def is_paid_event(self) -> bool:
        """Formule payante (hors gratuit)."""
        if self.plan_id:
            plan = self.plan
            if plan.is_free:
                return False
            if plan.is_custom:
                return False
            return (plan.price or 0) > 0
        return (self.price_snapshot or 0) > 0

    @property
    def needs_payment(self) -> bool:
        """Payant et pas encore actif : l'espace événement reste fermé."""
        return self.status == self.STATUS_PENDING_PAYMENT and self.is_paid_event

    @property
    def is_archived(self) -> bool:
        return self.status in {self.STATUS_ARCHIVED, self.STATUS_COMPLETED}

    @property
    def is_grand_event(self) -> bool:
        if self.plan_id and getattr(self.plan, "slug", "") == self.GRAND_PLAN_SLUG:
            return True
        name = (self.plan_name_snapshot or "").strip().casefold()
        return name in {"grand événement", "grand evenement"}

    @property
    def type_label(self) -> str:
        custom = (self.event_type_custom or "").strip()
        if self.event_type == self.TYPE_OTHER and custom:
            return custom
        try:
            cat = EventCategory.objects.filter(slug=self.event_type).first()
        except Exception:
            cat = None
        if cat:
            return cat.name
        return dict(self.TYPE_CHOICES).get(self.event_type, self.event_type)

    def display_date(self) -> str:
        if self.date:
            return self.date.strftime("%d/%m/%Y")
        return ""

    def display_date_long(self) -> str:
        if not self.date:
            return ""
        jours = (
            "LUNDI",
            "MARDI",
            "MERCREDI",
            "JEUDI",
            "VENDREDI",
            "SAMEDI",
            "DIMANCHE",
        )
        mois = (
            "",
            "JANVIER",
            "FÉVRIER",
            "MARS",
            "AVRIL",
            "MAI",
            "JUIN",
            "JUILLET",
            "AOÛT",
            "SEPTEMBRE",
            "OCTOBRE",
            "NOVEMBRE",
            "DÉCEMBRE",
        )
        d = self.date
        return f"{jours[d.weekday()]} {d.day} {mois[d.month]} {d.year}"

    def display_time(self) -> str:
        if self.start_time:
            return self.start_time.strftime("%H:%M")
        return ""

    def starts_at_iso(self) -> str:
        if not self.date:
            return ""
        t = self.start_time or time(0, 0)
        dt = datetime.combine(self.date, t)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt.isoformat()

    @property
    def display_primary_color(self) -> str:
        return display_color(self.primary_color)

    @property
    def has_custom_cover(self) -> bool:
        return bool(self.flyer)

    @property
    def has_custom_logo(self) -> bool:
        return bool(self.logo)

    def _category_cover_slug(self) -> str:
        slug = (self.event_type or "").strip()
        custom = (self.event_type_custom or "").strip().lower()
        if slug == self.TYPE_OTHER and custom:
            try:
                for cat in EventCategory.objects.exclude(slug=self.TYPE_OTHER):
                    name = (cat.name or "").strip().lower()
                    if name and name in custom:
                        return cat.slug
            except Exception:
                pass
        return slug

    @property
    def cover_url(self) -> str:
        if self.flyer:
            try:
                return self.flyer.url
            except ValueError:
                pass
        from .branding import DEFAULT_COVER, category_cover_url, default_cover_url

        url = category_cover_url(self._category_cover_slug())
        generic = DEFAULT_COVER.rsplit("/", 1)[-1]
        if url and url.rstrip("/").endswith(generic):
            site = default_cover_url()
            if site and not site.rstrip("/").endswith(generic):
                return site
        return url

    @property
    def logo_display_url(self) -> str:
        if self.logo:
            try:
                return self.logo.url
            except ValueError:
                pass
        return default_logo_url()

    def ceremony_context(self) -> dict:
        """Contexte d'affichage pour invitations / flyer (remplace CEREMONY settings)."""
        return {
            "title": self.name,
            "subtitle": self.type_label,
            "date": self.display_date() or "Date à confirmer",
            "time": self.display_time() or "Heure à confirmer",
            "venue": self.venue or "Lieu à confirmer",
            "organizer": self.organizer_name or self.owner.get_username(),
            "footer": (self.invitation_message or "").strip()
            or "Veuillez présenter cette invitation à l'entrée.",
            "description": self.description,
            "welcome": (self.welcome_text or "").strip()
            or "Vous êtes cordialement invité(e)",
            "primary_color": self.display_primary_color,
            "flyer_url": self.cover_url,
            "logo_url": self.logo_display_url,
        }

    @property
    def is_custom_plan(self) -> bool:
        return bool(self.plan_id and self.plan.is_custom)

    @property
    def invite_form_locked(self) -> bool:
        return self.invite_published_at is not None

    @property
    def uses_paid_guest_link(self) -> bool:
        return self.is_ticketing or self.is_custom_plan

    @property
    def listed_publicly(self) -> bool:
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.is_ticketing and self.invite_link_enabled:
            return True
        return bool(self.is_public or self.show_on_homepage)

    @property
    def cheapest_ticket_price(self):
        prices = [t.price for t in self.ticket_tiers.all() if t.is_active]
        return min(prices) if prices else None

    def public_category_group(self) -> str:
        slug = (self.event_type or "").strip()
        custom = (self.event_type_custom or "").casefold()
        if slug == self.TYPE_WEDDING or "mariage" in custom:
            return "mariage"
        concert_hints = ("concert", "festival", "enb", "showcase", "live")
        if slug in {self.TYPE_CONCERT, self.TYPE_GALA} or any(k in custom for k in concert_hints):
            return "concert"
        return "autres"


def public_tier_name(name: str) -> str:
    key = (name or "").strip().casefold()
    if key in {"early bird", "early-bird", "earlybird"}:
        return "Prévente"
    return name or ""


class TicketTier(models.Model):
    """Catégorie de billet pour la billetterie (Standard, VIP, prévente…)."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="ticket_tiers",
    )
    name = models.CharField("Type", max_length=80)
    description = models.CharField("Description", max_length=200, blank=True, default="")
    price = models.DecimalField("Prix", max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(
        "Quantité",
        default=0,
        help_text="0 = illimité.",
    )
    is_active = models.BooleanField("Actif", default=True)
    display_order = models.PositiveIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "price", "id"]
        verbose_name = "Catégorie de billet"
        verbose_name_plural = "Catégories de billets"

    def __str__(self):
        return f"{self.name} — {self.event_id}"

    @property
    def public_name(self) -> str:
        return public_tier_name(self.name)

    @property
    def sold_count(self) -> int:
        return self.invitations.filter(status=Invitation.STATUS_VALID).count()

    @property
    def remaining(self) -> int | None:
        if not self.quantity:
            return None
        return max(0, int(self.quantity) - self.sold_count)

    @property
    def sold_out(self) -> bool:
        remaining = self.remaining
        return remaining is not None and remaining <= 0


class EventController(models.Model):
    """Accès scan pour un contrôleur (lien unique + code défini par l’organisateur)."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="controllers",
    )
    label = models.CharField("Nom du contrôleur", max_length=120, default="Contrôleur")
    token = models.CharField("Jeton", max_length=40, unique=True, db_index=True)
    access_code = models.CharField("Code de vérification", max_length=40)
    is_active = models.BooleanField("Actif", default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contrôleur"
        verbose_name_plural = "Contrôleurs"

    def __str__(self):
        return f"{self.label} ({self.event_id})"


class EventLimitAdjustment(models.Model):
    """Ajustement administratif exceptionnel des limites d'un événement."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="limit_adjustments",
    )
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="event_limit_adjustments",
    )
    previous_regular = models.PositiveIntegerField(null=True, blank=True)
    previous_vip = models.PositiveIntegerField(null=True, blank=True)
    previous_total = models.PositiveIntegerField(null=True, blank=True)
    new_regular = models.PositiveIntegerField(null=True, blank=True)
    new_vip = models.PositiveIntegerField(null=True, blank=True)
    new_total = models.PositiveIntegerField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ajustement de limite"
        verbose_name_plural = "Ajustements de limites"

    def __str__(self):
        return f"Ajustement {self.event_id} @ {self.created_at}"


# ---------------------------------------------------------------------------
# Invitations / scans / admissions
# ---------------------------------------------------------------------------


class Invitation(models.Model):
    """
    Billet d'invitation unifié (standard ou VIP), rattaché à un Event.

    - ``code`` : unique (invitations PREFIX-XXXXXX / VIP-XXXXXX, billets GEB-XXXX-XXXX)
    - ``places`` / ``places_used`` : capacité et consommation
    """

    STATUS_VALID = "valide"
    STATUS_INVALID = "invalide"
    STATUS_DISABLED = "desactive"
    STATUS_CHOICES = [
        (STATUS_VALID, "Valide"),
        (STATUS_INVALID, "Invalide"),
        (STATUS_DISABLED, "Annulée"),
    ]

    TYPE_RECIPIENT = PARTICIPANT_RECIPIENT
    TYPE_VIP = PARTICIPANT_VIP
    TYPE_CHOICES = [
        (TYPE_RECIPIENT, "Standard"),
        (TYPE_VIP, "VIP"),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True,
    )
    code = models.CharField("Code", max_length=64, unique=True, db_index=True)
    last_name = models.CharField("Nom", max_length=120)
    first_name = models.CharField("Prénom", max_length=120)
    participant_type = models.CharField(
        "Type",
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_RECIPIENT,
        db_index=True,
    )
    category = models.CharField("Catégorie", max_length=80, blank=True, default="")
    places = models.PositiveIntegerField(
        "Places autorisées",
        default=1,
        help_text="Toujours 1 : une invitation = une personne.",
    )
    places_used = models.PositiveIntegerField("Places utilisées", default=0)
    status = models.CharField(
        "Statut",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_VALID,
    )
    imported_at = models.DateTimeField("Date d'import", default=timezone.now)
    is_validated = models.BooleanField(
        "Présent (au moins une entrée)",
        default=False,
        db_index=True,
    )
    validated_at = models.DateTimeField(
        "Première entrée",
        null=True,
        blank=True,
    )
    scan_count = models.PositiveIntegerField("Nombre de scans", default=0)
    invitation_generated = models.BooleanField("Invitation générée", default=False)
    invitation_generated_at = models.DateTimeField(null=True, blank=True)
    invitation_sent = models.BooleanField("Invitation envoyée", default=False)
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    SOURCE_IMPORT = "import"
    SOURCE_FORM = "form"
    SOURCE_CHOICES = [
        (SOURCE_IMPORT, "Excel / import"),
        (SOURCE_FORM, "Formulaire public"),
    ]
    email = models.EmailField("E-mail", blank=True, default="")
    phone = models.CharField("Téléphone", max_length=40, blank=True, default="")
    extra_data = models.JSONField("Champs complémentaires", default=dict, blank=True)
    ticket_tier = models.ForeignKey(
        "TicketTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations",
    )
    source = models.CharField(
        "Origine",
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_IMPORT,
        db_index=True,
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"
        indexes = [
            models.Index(fields=["event", "participant_type"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_code(self) -> str:
        from .code_service import display_access_code

        return display_access_code(self.code)

    @property
    def places_allowed(self):
        return self.places

    @property
    def places_remaining(self):
        return max(0, self.places - self.places_used)

    @property
    def is_active_ticket(self):
        return self.status == self.STATUS_VALID

    @property
    def is_exhausted(self):
        return self.places_remaining <= 0

    @property
    def is_vip(self):
        return self.participant_type == self.TYPE_VIP

    @property
    def is_cancelled_ticket(self):
        return self.status == self.STATUS_DISABLED

    @property
    def invitation_lifecycle(self):
        if self.status == self.STATUS_DISABLED:
            return "cancelled"
        if self.is_validated or self.places_used > 0:
            return "present"
        if self.invitation_sent:
            return "sent"
        if self.invitation_generated:
            return "generated"
        return "todo"

    def sync_presence_flags(self):
        """Keep is_validated / validated_at aligned with places_used."""
        if self.places_used > 0:
            self.is_validated = True
            if not self.validated_at:
                self.validated_at = timezone.now()
        else:
            self.is_validated = False
            self.validated_at = None


class ScanLog(models.Model):
    """Journal d'audit : chaque lookup / tentative (succès ou échec)."""

    RESULT_VALID = "valid"
    RESULT_ALREADY_USED = "already_used"
    RESULT_INVALID = "invalid"
    RESULT_DISABLED = "disabled"
    RESULT_RECOGNIZED = "recognized"
    RESULT_ADMITTED = "admitted"
    RESULT_CHOICES = [
        (RESULT_VALID, "Valide"),
        (RESULT_ALREADY_USED, "Épuisée"),
        (RESULT_INVALID, "Inconnu"),
        (RESULT_DISABLED, "Désactivé"),
        (RESULT_RECOGNIZED, "Reconnue"),
        (RESULT_ADMITTED, "Entrée enregistrée"),
    ]

    invitation = models.ForeignKey(
        Invitation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_logs",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_logs",
    )
    code_scanned = models.CharField(max_length=64)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    scanned_at = models.DateTimeField(default=timezone.now, db_index=True)
    agent = models.CharField(max_length=120, blank=True, default="")
    persons = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-scanned_at"]
        verbose_name = "Journal de scan"
        verbose_name_plural = "Journaux de scan"

    def __str__(self):
        return f"{self.code_scanned} → {self.result} @ {self.scanned_at}"


class Admission(models.Model):
    """Confirmation d'entrée (une ligne peut couvrir plusieurs personnes)."""

    invitation = models.ForeignKey(
        Invitation,
        on_delete=models.CASCADE,
        related_name="admissions",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="admissions",
        null=True,
        blank=True,
    )
    persons = models.PositiveIntegerField()
    admitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    agent = models.CharField(max_length=120, blank=True, default="")
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-admitted_at"]
        verbose_name = "Admission"
        verbose_name_plural = "Admissions"

    def __str__(self):
        return f"{self.invitation.code} +{self.persons} @ {self.admitted_at}"


# ---------------------------------------------------------------------------
# Paiements & audit
# ---------------------------------------------------------------------------


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_SUCCESS, "Réussi"),
        (STATUS_FAILED, "Échoué"),
        (STATUS_CANCELLED, "Annulé"),
        (STATUS_REFUNDED, "Remboursé"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.ForeignKey(
        EventPlan,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="XOF")
    provider = models.CharField(max_length=40, default="mock")
    provider_reference = models.CharField(
        max_length=120,
        blank=True,
        default="",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"

    def __str__(self):
        return f"{self.provider_reference or self.pk} ({self.status})"


class GuestPayment(models.Model):
    """Paiement d’un invité (billetterie / lien payant) via SingPay."""

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_SUCCESS, "Réussi"),
        (STATUS_FAILED, "Échoué"),
    ]
    PAYOUT_PENDING = "pending"
    PAYOUT_PROCESSING = "processing"
    PAYOUT_RECORDED = "recorded"
    PAYOUT_FAILED = "failed"
    PAYOUT_CHOICES = [
        (PAYOUT_PENDING, "À reverser"),
        (PAYOUT_PROCESSING, "En cours"),
        (PAYOUT_RECORDED, "Reversé"),
        (PAYOUT_FAILED, "Échec"),
    ]

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guest_payments",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="guest_payments",
    )
    invitation = models.OneToOneField(
        "Invitation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_payment",
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    extra_data = models.JSONField(default=dict, blank=True)
    participant_type = models.CharField(
        max_length=20,
        choices=Invitation.TYPE_CHOICES,
        default=Invitation.TYPE_RECIPIENT,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="XOF")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    provider = models.CharField(max_length=40, default="mock")
    provider_reference = models.CharField(max_length=120, blank=True, default="", db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    payout_status = models.CharField(
        max_length=20,
        choices=PAYOUT_CHOICES,
        default=PAYOUT_PENDING,
        db_index=True,
    )
    payout = models.ForeignKey(
        "OrganizerPayout",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_payments",
    )
    payout_reference = models.CharField(max_length=120, blank=True, default="")
    payout_error = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Paiement invité"
        verbose_name_plural = "Paiements invités"

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.amount} ({self.status})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class OrganizerPayout(models.Model):
    """Reversement Mobile Money vers l’organisateur, déclenché depuis l’admin."""

    STATUS_PENDING = "pending"
    STATUS_PARTIAL = "partial"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En cours"),
        (STATUS_PARTIAL, "Partiel"),
        (STATUS_SUCCESS, "Réussi"),
        (STATUS_FAILED, "Échoué"),
    ]

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organizer_payouts",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_payouts",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="XOF")
    momo_operator = models.CharField(
        max_length=16,
        blank=True,
        default="",
        choices=UserProfile.MOMO_CHOICES,
    )
    momo_phone = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    provider = models.CharField(max_length=40, default="mock")
    provider_reference = models.CharField(max_length=120, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Reversement organisateur"
        verbose_name_plural = "Reversements organisateurs"

    def __str__(self):
        return f"{self.organizer} — {self.amount} ({self.status})"


class AdminAuditLog(models.Model):
    ACTION_PLAN_UPDATE = "plan_update"
    ACTION_LIMIT_ADJUST = "limit_adjust"
    ACTION_EVENT_ACTIVATE = "event_activate"
    ACTION_PAYMENT_CHANGE = "payment_change"
    ACTION_PAYOUT = "payout"
    ACTION_EVENT_CANCEL = "event_cancel"
    ACTION_OTHER = "other"
    ACTION_CHOICES = [
        (ACTION_PLAN_UPDATE, "Modification formule"),
        (ACTION_LIMIT_ADJUST, "Ajustement limite"),
        (ACTION_EVENT_ACTIVATE, "Activation manuelle"),
        (ACTION_PAYMENT_CHANGE, "Changement paiement"),
        (ACTION_PAYOUT, "Reversement Mobile Money"),
        (ACTION_EVENT_CANCEL, "Annulation"),
        (ACTION_OTHER, "Autre"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="admin_audit_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=60, blank=True, default="")
    target_id = models.CharField(max_length=60, blank=True, default="")
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Journal d'activité admin"
        verbose_name_plural = "Journaux d'activité admin"

    def __str__(self):
        return f"{self.action}: {self.summary}"


# ---------------------------------------------------------------------------
# Console plateforme — site, médias, catégories
# ---------------------------------------------------------------------------


class SiteSettings(models.Model):
    """Singleton — configuration centralisée de Gab Event."""

    SINGPAY_SANDBOX = "sandbox"
    SINGPAY_PRODUCTION = "production"
    SINGPAY_ENV_CHOICES = (
        (SINGPAY_SANDBOX, "Sandbox (tests)"),
        (SINGPAY_PRODUCTION, "Production"),
    )

    site_name = models.CharField("Nom du site", max_length=80, default="Gab Event")
    tagline = models.CharField(
        "Accroche",
        max_length=180,
        blank=True,
        default="Invitations électroniques, avec élégance.",
    )
    logo = models.ImageField(
        "Logo du site",
        upload_to="site/",
        blank=True,
        null=True,
    )
    default_cover = models.ImageField(
        "Image par défaut / bannière",
        upload_to="site/",
        blank=True,
        null=True,
    )
    hero_image = models.ImageField(
        "Image hero (accueil)",
        upload_to="site/",
        blank=True,
        null=True,
    )
    auth_login_image = models.ImageField(
        "Image pages de connexion",
        upload_to="site/",
        blank=True,
        null=True,
        help_text="Fond des écrans login / inscription / mot de passe. Vide = image hero, sinon galerie.",
    )
    hero_line1 = models.CharField(
        "Titre hero — ligne 1",
        max_length=120,
        blank=True,
        default="Vos invitations électroniques",
    )
    hero_line2 = models.CharField(
        "Titre hero — ligne 2",
        max_length=120,
        blank=True,
        default="en une minute",
    )
    hero_lead = models.TextField(
        "Sous-titre hero",
        blank=True,
        default=(
            "Créez votre événement, envoyez vos billets électroniques "
            "et gérez vos invités depuis votre smartphone."
        ),
    )
    hero_cta_guest = models.CharField(
        "Bouton hero (visiteur)",
        max_length=80,
        blank=True,
        default="Commencer gratuitement",
    )
    hero_cta_user = models.CharField(
        "Bouton hero (connecté)",
        max_length=80,
        blank=True,
        default="Créer un événement",
    )
    banner_enabled = models.BooleanField("Afficher la bannière promo", default=False)
    banner_text = models.CharField("Texte de la bannière", max_length=200, blank=True, default="")
    banner_link = models.URLField("Lien de la bannière", blank=True, default="")
    banner_link_label = models.CharField(
        "Libellé du lien bannière",
        max_length=40,
        blank=True,
        default="Voir",
    )
    support_email = models.EmailField("E-mail support", blank=True, default="")
    support_phone = models.CharField("Téléphone support", max_length=32, blank=True, default="")
    whatsapp_number = models.CharField(
        "Numéro WhatsApp",
        max_length=32,
        blank=True,
        default="",
        help_text="Ex. 077012345 ou +24177012345",
    )
    whatsapp_message = models.CharField(
        "Message WhatsApp prérempli",
        max_length=180,
        blank=True,
        default="Bonjour, j’ai une question sur Gab Event.",
    )
    facebook_url = models.URLField("Facebook", blank=True, default="")
    instagram_url = models.URLField("Instagram", blank=True, default="")
    tiktok_url = models.URLField("TikTok", blank=True, default="")
    youtube_url = models.URLField("YouTube", blank=True, default="")
    linkedin_url = models.URLField("LinkedIn", blank=True, default="")
    x_url = models.URLField("X (Twitter)", blank=True, default="")
    public_base_url = models.URLField(
        "URL publique du site",
        blank=True,
        default="",
        help_text="Retours de paiement SingPay. Ex. https://gabevent.com",
    )
    play_store_url = models.URLField("Lien Google Play", blank=True, default="")
    app_store_url = models.URLField("Lien App Store", blank=True, default="")
    extra_link_label = models.CharField(
        "Lien personnalisé — libellé",
        max_length=40,
        blank=True,
        default="",
    )
    extra_link_url = models.URLField("Lien personnalisé — URL", blank=True, default="")
    meta_description = models.CharField(
        "Description SEO",
        max_length=220,
        blank=True,
        default="",
        help_text="Balise meta des pages publiques. Vide = accroche.",
    )
    default_from_email = models.EmailField(
        "E-mail d’expédition",
        blank=True,
        default="",
        help_text="Expéditeur des e-mails (mot de passe oublié…). Vide = e-mail support.",
    )
    allow_mock_payments = models.BooleanField(
        "Autoriser les paiements de test",
        default=True,
        help_text="Uniquement en DEBUG. Décochez pour forcer SingPay.",
    )
    singpay_api_key = models.CharField("SingPay — clé API", max_length=200, blank=True, default="")
    singpay_api_secret = models.CharField(
        "SingPay — secret API",
        max_length=300,
        blank=True,
        default="",
    )
    singpay_merchant_id = models.CharField(
        "SingPay — portefeuille",
        max_length=120,
        blank=True,
        default="",
    )
    singpay_disbursement_id = models.CharField(
        "SingPay — disbursement",
        max_length=120,
        blank=True,
        default="",
    )
    singpay_environment = models.CharField(
        "Environnement SingPay",
        max_length=20,
        choices=SINGPAY_ENV_CHOICES,
        default=SINGPAY_SANDBOX,
    )
    updated_at = models.DateTimeField(auto_now=True)
    commission_regular_pct = models.DecimalField(
        "Commission standard (%)",
        max_digits=5,
        decimal_places=2,
        default=10,
    )
    commission_vip_pct = models.DecimalField(
        "Commission VIP (%)",
        max_digits=5,
        decimal_places=2,
        default=20,
    )
    commission_pct = models.DecimalField(
        "Commission unique (%)",
        max_digits=5,
        decimal_places=2,
        default=7,
        help_text="Taux unique entre 6 et 8 %, appliqué à chaque billet payant.",
    )
    commission_fixed = models.DecimalField(
        "Frais fixe par billet (F CFA)",
        max_digits=10,
        decimal_places=2,
        default=150,
    )
    payout_sla_hours = models.PositiveIntegerField(
        "Délai de reversement (heures ouvrées)",
        default=72,
    )
    singpay_fees_on_platform = models.BooleanField(
        "Gab Event prend en charge les frais SingPay",
        default=False,
        help_text="Si coché, les frais SingPay ne sont pas déduits du reversement organisateur.",
    )
    animated_card_price = models.DecimalField(
        "Prix carte animée (F CFA)",
        max_digits=10,
        decimal_places=2,
        default=25000,
    )
    legal_company_name = models.CharField(
        "Raison sociale (facture)",
        max_length=160,
        blank=True,
        default="Gab Event",
    )
    legal_nif = models.CharField(
        "NIF",
        max_length=40,
        blank=True,
        default="",
        help_text="Obligatoire pour qu’une entreprise gabonaise puisse payer.",
    )
    legal_rccm = models.CharField(
        "RCCM",
        max_length=40,
        blank=True,
        default="",
    )
    legal_address = models.CharField(
        "Adresse (facture)",
        max_length=255,
        blank=True,
        default="",
    )
    legal_city = models.CharField(
        "Ville (facture)",
        max_length=120,
        blank=True,
        default="Libreville",
    )
    legal_phone = models.CharField(
        "Téléphone (facture)",
        max_length=40,
        blank=True,
        default="",
    )
    legal_email = models.EmailField(
        "E-mail (facture)",
        blank=True,
        default="",
    )
    lifetime_events = models.PositiveIntegerField(
        "Compteur cumulatif — événements",
        default=0,
    )
    lifetime_invitations = models.PositiveIntegerField(
        "Compteur cumulatif — invitations",
        default=0,
    )
    lifetime_organizers = models.PositiveIntegerField(
        "Compteur cumulatif — organisateurs",
        default=0,
    )

    class Meta:
        verbose_name = "Réglages du site"
        verbose_name_plural = "Réglages du site"

    def __str__(self):
        return self.site_name

    @classmethod
    def load(cls) -> "SiteSettings":
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    def whatsapp_href(self) -> str:
        raw = (self.whatsapp_number or "").strip()
        if not raw:
            return ""
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0") and 8 <= len(digits) <= 10:
            digits = "241" + digits.lstrip("0")
        if not digits:
            return ""
        text = (self.whatsapp_message or "").strip() or f"Bonjour, j’ai une question sur {self.site_name}."
        from urllib.parse import quote

        return f"https://wa.me/{digits}?text={quote(text)}"

    def payout_policy_text(self) -> str:
        hours = self.payout_sla_hours or 72
        pct = self.commission_pct or self.commission_regular_pct or 7
        return (
            f"Commission : {pct} % du prix de chaque billet. "
            f"Reversement sous {hours}h ouvrées maximum après votre demande."
        )

    def social_items(self) -> list[dict]:
        mapping = (
            ("facebook_url", "Facebook"),
            ("instagram_url", "Instagram"),
            ("tiktok_url", "TikTok"),
            ("youtube_url", "YouTube"),
            ("linkedin_url", "LinkedIn"),
            ("x_url", "X"),
        )
        items = []
        for field, label in mapping:
            url = (getattr(self, field) or "").strip()
            if url:
                items.append({"key": field.replace("_url", ""), "label": label, "url": url})
        return items

    def has_singpay_keys(self) -> bool:
        return bool(self.singpay_api_key and self.singpay_api_secret and self.singpay_merchant_id)


class GalleryImage(models.Model):
    """Images du carrousel public et fonds par défaut."""

    image = models.ImageField(
        "Image",
        upload_to="gallery/%Y/%m/",
        blank=True,
        null=True,
    )
    static_path = models.CharField(
        "Fichier statique (interne)",
        max_length=200,
        blank=True,
        default="",
    )
    label = models.CharField("Titre", max_length=120)
    caption = models.CharField("Légende", max_length=200, blank=True, default="")
    is_active = models.BooleanField("Visible", default=True)
    display_order = models.PositiveIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "Image de galerie"
        verbose_name_plural = "Images de galerie"

    def __str__(self):
        return self.label

    @property
    def url(self) -> str:
        if self.image:
            try:
                return self.image.url
            except ValueError:
                pass
        if self.static_path:
            from .branding import static_url

            return static_url(self.static_path)
        return ""


class EventCategory(models.Model):
    """Types d'événements proposés à la création."""

    slug = models.SlugField(unique=True, max_length=40)
    name = models.CharField("Nom", max_length=80)
    icon_key = models.CharField("Icône", max_length=40, blank=True, default="")
    default_image = models.ImageField(
        "Photo par défaut",
        upload_to="categories/%Y/%m/",
        blank=True,
        null=True,
        help_text="Utilisée automatiquement si l’organisateur n’ajoute pas de visuel.",
    )
    default_image_static = models.CharField(
        "Fichier statique (interne)",
        max_length=200,
        blank=True,
        default="",
    )
    is_active = models.BooleanField("Actif", default=True)
    is_custom_entry = models.BooleanField(
        "Permet un type libre",
        default=False,
        help_text="Ex. Personnalisé — l'organisateur nomme son type.",
    )
    display_order = models.PositiveIntegerField("Ordre", default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Catégorie d'événement"
        verbose_name_plural = "Catégories d'événements"

    def __str__(self):
        return self.name

    @property
    def image_url(self) -> str:
        if self.default_image:
            try:
                return self.default_image.url
            except ValueError:
                pass
        if self.default_image_static:
            from .branding import static_url

            return static_url(self.default_image_static)
        return ""


class FaqItem(models.Model):
    """Questions affichées sur /faq/ — éditables depuis la console."""

    SECTION_START = "start"
    SECTION_EVENTS = "events"
    SECTION_INVITES = "invites"
    SECTION_PAYMENTS = "payments"
    SECTION_SCAN = "scan"
    SECTION_ACCOUNT = "account"
    SECTION_CHOICES = (
        (SECTION_START, "Démarrer"),
        (SECTION_EVENTS, "Événements"),
        (SECTION_INVITES, "Invitations"),
        (SECTION_PAYMENTS, "Paiements"),
        (SECTION_SCAN, "Contrôle d’accès"),
        (SECTION_ACCOUNT, "Compte"),
    )

    question = models.CharField("Question", max_length=220)
    answer = models.TextField("Réponse")
    section = models.CharField(
        "Rubrique",
        max_length=20,
        choices=SECTION_CHOICES,
        default=SECTION_START,
    )
    display_order = models.PositiveIntegerField("Ordre", default=0)
    is_active = models.BooleanField("Visible", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section", "display_order", "id"]
        verbose_name = "Question FAQ"
        verbose_name_plural = "Questions FAQ"

    def __str__(self):
        return self.question
