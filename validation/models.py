"""
Modèles métier — invitations, journaux de scan, admissions.

Flux terrain :
  1. Scan / saisie → ScanLog + statut recognized | already_used | invalid
  2. Confirmation du nombre de personnes → Admission (places_used atomique)
"""
from django.db import models
from django.utils import timezone

from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP


class Invitation(models.Model):
    """
    Billet d'invitation unifié (récipiendaire ou VIP).

    - ``code`` : ATC24-XXXXXX ou VIP-XXXXXX (unique)
    - ``places`` / ``places_used`` : capacité et consommation
    - Le lookup (scan) n'incrémente que ``scan_count`` ; l'admission consomme des places.
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
        (TYPE_RECIPIENT, "Récipiendaire"),
        (TYPE_VIP, "VIP"),
    ]

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

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"

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
