"""
Modèles métier — plateforme multi-événements Gab Event.

Hiérarchie :
  User → EventPlan / Event → Invitation → ScanLog / Admission
  Payment, UserProfile, AdminAuditLog, EventLimitAdjustment
"""
from __future__ import annotations

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
        help_text="Suppression automatique N jours après la création. Vide pour une fenêtre définie à la création (Personnalisé).",
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
            return "Fenêtre définie à la création"
        n = int(self.lifetime_days)
        return f"Conservé {n} jour{'s' if n > 1 else ''}"


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
        (TYPE_BIRTHDAY, "Anniversaire"),
        (TYPE_RECEPTION, "Réception"),
        (TYPE_PROFESSIONAL, "Événement professionnel"),
        (TYPE_OTHER, "Personnalisé"),
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
        "Suppression automatique le",
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

    def save(self, *args, **kwargs):
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
        if (
            self.pk
            and not self.expires_at
            and self.plan_id
            and not self.is_legacy
        ):
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
        """Calcule la fenêtre de vie et, si besoin, celle du lien d’invitation."""
        if starts:
            self.validity_starts_on = starts
        if ends:
            self.validity_ends_on = ends
        created = self.created_at or timezone.now()
        plan = self.plan if self.plan_id else None
        if plan and plan.is_custom:
            if not self.validity_starts_on:
                self.validity_starts_on = timezone.localdate()
            if not self.validity_ends_on:
                self.validity_ends_on = self.validity_starts_on + timedelta(days=30)
            end_dt = datetime.combine(self.validity_ends_on, time(23, 59, 59))
            self.expires_at = timezone.make_aware(end_dt, timezone.get_current_timezone())
        else:
            days = None
            if plan and plan.lifetime_days:
                days = int(plan.lifetime_days)
            elif plan:
                days = self.LIFETIME_BY_SLUG.get(plan.slug)
            days = days or 14
            self.validity_starts_on = created.date()
            self.expires_at = created + timedelta(days=days)
            self.validity_ends_on = timezone.localtime(self.expires_at).date()
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

    def display_time(self) -> str:
        if self.start_time:
            return self.start_time.strftime("%H:%M")
        return ""

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
        return self.is_custom_plan


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

    - ``code`` : unique globalement (ATC24-XXXXXX, VIP-XXXXXX, PREFIX-XXXXXX…)
    - ``places`` / ``places_used`` : capacité et consommation
    """

    STATUS_VALID = "valide"
    STATUS_INVALID = "invalide"
    STATUS_DISABLED = "desactive"
    STATUS_CHOICES = [
        (STATUS_VALID, "Valide"),
        (STATUS_INVALID, "Invalide"),
        (STATUS_DISABLED, "Désactivé"),
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
    def invitation_lifecycle(self):
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
    """Paiement d’un invité (formule Personnalisé) via SingPay."""

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
    """Singleton — identité publique de Gab Event."""

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
        "Image par défaut des événements",
        upload_to="site/",
        blank=True,
        null=True,
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
