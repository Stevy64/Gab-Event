"""
Logique métier : import Excel, lookup, admission atomique, stats, export.

Règle importante :
  - ``lookup_invitation`` identifie sans consommer de places
  - ``admit_persons`` consomme N places sous transaction / select_for_update
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from .code_service import generate_invitation_code, normalize_code
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Admission, Invitation, ScanLog

# re-export for callers
__all__ = [
    "normalize_code",
    "import_invitations_from_workbook",
    "import_invitations_from_path",
    "lookup_invitation",
    "validate_invitation",
    "admit_persons",
    "cancel_validation",
    "dashboard_stats",
    "search_invitations",
    "export_attendance_response",
    "mark_invitation_sent",
]


def normalize_status(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    mapping = {
        "valide": Invitation.STATUS_VALID,
        "valid": Invitation.STATUS_VALID,
        "ok": Invitation.STATUS_VALID,
        "invalide": Invitation.STATUS_INVALID,
        "invalid": Invitation.STATUS_INVALID,
        "desactive": Invitation.STATUS_DISABLED,
        "désactivé": Invitation.STATUS_DISABLED,
        "desactivee": Invitation.STATUS_DISABLED,
        "disabled": Invitation.STATUS_DISABLED,
        "annule": Invitation.STATUS_DISABLED,
        "annulé": Invitation.STATUS_DISABLED,
    }
    return mapping.get(value, Invitation.STATUS_VALID)


def normalize_participant_type(raw: str | None, category: str = "") -> str:
    value = (raw or "").strip().upper()
    mapping = {
        "RECIPIENT": PARTICIPANT_RECIPIENT,
        "RECIPIENDAIRE": PARTICIPANT_RECIPIENT,
        "DIPLOME": PARTICIPANT_RECIPIENT,
        "DIPLÔMÉ": PARTICIPANT_RECIPIENT,
        "ATC": PARTICIPANT_RECIPIENT,
        "VIP": PARTICIPANT_VIP,
        "SPECIAL": PARTICIPANT_VIP,
        "SPÉCIAL": PARTICIPANT_VIP,
        "INVITE": PARTICIPANT_VIP,
        "INVITÉ": PARTICIPANT_VIP,
    }
    if value in mapping:
        return mapping[value]
    cat = (category or "").strip().lower()
    if any(
        k in cat
        for k in (
            "instruct",
            "direction",
            "officiel",
            "encadr",
            "vip",
            "spécial",
            "special",
            "responsable",
        )
    ):
        return PARTICIPANT_VIP
    if "récipiendaire" in cat or "recipiendaire" in cat or "diplôm" in cat:
        return PARTICIPANT_RECIPIENT
    return PARTICIPANT_RECIPIENT


def _cell(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        for existing in row:
            if str(existing).strip().lower() == key.lower():
                value = row[existing]
                if value is None:
                    return default
                return str(value).strip()
    return default


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return self.created + self.updated


def import_invitations_from_workbook(workbook) -> ImportResult:
    """Import / upsert invitations. Never regenerates existing codes."""
    result = ImportResult()
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        result.errors.append("Le fichier Excel est vide.")
        return result

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    header_map = {h.lower(): idx for idx, h in enumerate(headers) if h}
    has_prenom = "prenom" in header_map or "prénom" in header_map
    if "nom" not in header_map or not has_prenom:
        result.errors.append(
            "Colonnes manquantes : Nom, Prenom. "
            "Optionnelles : Code, Type, Categorie, Places, Statut."
        )
        return result

    seen_codes: set[str] = set()

    for line_no, values in enumerate(rows[1:], start=2):
        if values is None or all(v is None or str(v).strip() == "" for v in values):
            continue

        row = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
        last_name = _cell(row, "nom")
        first_name = _cell(row, "prenom", "prénom")
        category = _cell(row, "categorie", "catégorie")
        type_raw = _cell(row, "type", "participant_type")
        places_raw = _cell(row, "places", default="1")
        status = normalize_status(_cell(row, "statut", "status", default="Valide"))
        code = normalize_code(_cell(row, "code"))
        participant_type = normalize_participant_type(type_raw, category)

        if not last_name or not first_name:
            result.errors.append(f"Ligne {line_no} : nom ou prénom manquant.")
            continue

        try:
            # Une invitation = une personne (places Excel ignorées si > 1)
            places = 1
            if places_raw not in ("", None):
                int(float(places_raw))  # valide le format si fourni
        except (TypeError, ValueError):
            result.errors.append(f"Ligne {line_no} : places invalides ({places_raw!r}).")
            continue

        if not category:
            category = (
                "Récipiendaire"
                if participant_type == PARTICIPANT_RECIPIENT
                else "VIP"
            )

        # Match existing by code if provided
        existing = None
        if code:
            if code in seen_codes:
                result.errors.append(
                    f"Ligne {line_no} : code en double dans le fichier ({code})."
                )
                continue
            existing = Invitation.objects.filter(code__iexact=code).first()

        if existing:
            # Never regenerate / change code
            existing.last_name = last_name
            existing.first_name = first_name
            existing.category = category
            existing.participant_type = participant_type
            existing.places = places
            existing.status = status
            existing.imported_at = timezone.now()
            existing.save(
                update_fields=[
                    "last_name",
                    "first_name",
                    "category",
                    "participant_type",
                    "places",
                    "status",
                    "imported_at",
                ]
            )
            seen_codes.add(existing.code)
            result.updated += 1
            continue

        # New invitation — generate code if missing
        if not code:
            code = generate_invitation_code(participant_type)
        elif Invitation.objects.filter(code__iexact=code).exists():
            result.errors.append(f"Ligne {line_no} : code déjà utilisé ({code}).")
            continue

        if code in seen_codes:
            result.errors.append(f"Ligne {line_no} : code en double ({code}).")
            continue
        seen_codes.add(code)

        Invitation.objects.create(
            code=code,
            last_name=last_name,
            first_name=first_name,
            category=category,
            participant_type=participant_type,
            places=places,
            status=status,
        )
        result.created += 1

    return result


def import_invitations_from_path(path: str | Path) -> ImportResult:
    path = Path(path)
    if not path.exists():
        result = ImportResult()
        result.errors.append(f"Fichier introuvable : {path}")
        return result
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return import_invitations_from_workbook(workbook)
    finally:
        workbook.close()


def guest_payload(invitation: Invitation) -> dict:
    return {
        "first_name": invitation.first_name,
        "last_name": invitation.last_name,
        "category": invitation.category,
        "participant_type": invitation.participant_type,
        "places": invitation.places,
        "places_allowed": invitation.places_allowed,
        "places_used": invitation.places_used,
        "places_remaining": invitation.places_remaining,
        "code": invitation.code,
        "is_vip": invitation.is_vip,
    }


@dataclass
class LookupResult:
    status: str
    guest: dict | None = None
    validated_at: datetime | None = None
    invitation: Invitation | None = None

    def to_dict(self) -> dict:
        payload = {"status": self.status}
        if self.guest is not None:
            payload["guest"] = self.guest
        if self.validated_at is not None:
            payload["validated_at"] = self.validated_at.isoformat()
        return payload


def lookup_invitation(code: str, agent: str = "") -> LookupResult:
    """
    Identify an invitation without consuming places.
    Statuses: recognized | already_used | invalid
    """
    normalized = normalize_code(code)
    if not normalized:
        ScanLog.objects.create(
            invitation=None,
            code_scanned=code or "",
            result=ScanLog.RESULT_INVALID,
            agent=agent,
        )
        return LookupResult(status="invalid")

    invitation = Invitation.objects.filter(code__iexact=normalized).first()
    if invitation is None:
        ScanLog.objects.create(
            invitation=None,
            code_scanned=normalized,
            result=ScanLog.RESULT_INVALID,
            agent=agent,
        )
        return LookupResult(status="invalid")

    Invitation.objects.filter(pk=invitation.pk).update(scan_count=F("scan_count") + 1)
    invitation.refresh_from_db(fields=["scan_count"])

    if not invitation.is_active_ticket:
        ScanLog.objects.create(
            invitation=invitation,
            code_scanned=normalized,
            result=ScanLog.RESULT_DISABLED,
            agent=agent,
        )
        return LookupResult(status="invalid")

    if invitation.is_exhausted:
        ScanLog.objects.create(
            invitation=invitation,
            code_scanned=normalized,
            result=ScanLog.RESULT_ALREADY_USED,
            agent=agent,
        )
        return LookupResult(
            status="already_used",
            guest=guest_payload(invitation),
            validated_at=invitation.validated_at,
            invitation=invitation,
        )

    ScanLog.objects.create(
        invitation=invitation,
        code_scanned=normalized,
        result=ScanLog.RESULT_RECOGNIZED,
        agent=agent,
    )
    return LookupResult(
        status="recognized",
        guest=guest_payload(invitation),
        invitation=invitation,
    )


# Backward-compatible alias used by older tests / callers
def validate_invitation(code: str, agent: str = "") -> LookupResult:
    return lookup_invitation(code, agent=agent)


@dataclass
class AdmitResult:
    status: str
    guest: dict | None = None
    admitted_at: datetime | None = None
    persons: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        payload = {"status": self.status, "persons": self.persons}
        if self.guest is not None:
            payload["guest"] = self.guest
            name = f"{self.guest.get('first_name', '')} {self.guest.get('last_name', '')}".strip()
            if self.status == "admitted" and name:
                payload["welcome"] = self.message or f"Bienvenue, {name} !"
        if self.admitted_at is not None:
            payload["admitted_at"] = self.admitted_at.isoformat()
        if self.message:
            payload["message"] = self.message
        return payload


def admit_persons(code: str, persons: int = 1, agent: str = "") -> AdmitResult:
    """
    Enregistre l'entrée d'une seule personne (1 invitation = 1 billet = 1 entrée).
    Le paramètre ``persons`` est ignoré (toujours 1) pour compatibilité API.
    """
    normalized = normalize_code(code)
    persons = 1

    if not normalized:
        return AdmitResult(status="invalid")

    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .filter(code__iexact=normalized)
            .first()
        )
        if invitation is None:
            return AdmitResult(status="invalid")

        if not invitation.is_active_ticket:
            return AdmitResult(status="invalid", message="Invitation désactivée.")

        # Normaliser : une seule place par billet
        if invitation.places != 1:
            invitation.places = 1
            invitation.save(update_fields=["places"])

        if invitation.places_used >= 1 or invitation.is_exhausted:
            return AdmitResult(
                status="already_used",
                guest=guest_payload(invitation),
                message="Cette invitation a déjà été utilisée.",
            )

        now = timezone.now()
        invitation.places_used = 1
        invitation.sync_presence_flags()
        invitation.save(
            update_fields=[
                "places_used",
                "is_validated",
                "validated_at",
            ]
        )

        Admission.objects.create(
            invitation=invitation,
            persons=1,
            admitted_at=now,
            agent=agent,
        )
        ScanLog.objects.create(
            invitation=invitation,
            code_scanned=normalized,
            result=ScanLog.RESULT_ADMITTED,
            agent=agent,
            persons=1,
        )

        guest = guest_payload(invitation)
        welcome = f"Bienvenue, {invitation.full_name} !"
        return AdmitResult(
            status="admitted",
            guest=guest,
            admitted_at=now,
            persons=1,
            message=welcome,
        )


def cancel_validation(invitation: Invitation) -> Invitation:
    """Reset all admissions / places used (admin correction)."""
    with transaction.atomic():
        invitation.admissions.filter(is_cancelled=False).update(is_cancelled=True)
        invitation.places_used = 0
        invitation.is_validated = False
        invitation.validated_at = None
        invitation.save(update_fields=["places_used", "is_validated", "validated_at"])
    return invitation


def mark_invitation_sent(invitation: Invitation, sent: bool = True) -> Invitation:
    invitation.invitation_sent = sent
    invitation.invitation_sent_at = timezone.now() if sent else None
    invitation.save(update_fields=["invitation_sent", "invitation_sent_at"])
    return invitation


def search_invitations(query: str):
    query = (query or "").strip()
    qs = Invitation.objects.all()
    if not query:
        return qs.none()
    return qs.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(code__icontains=normalize_code(query))
        | Q(category__icontains=query)
    )


def _type_stats(participant_type: str) -> dict:
    qs = Invitation.objects.filter(participant_type=participant_type)
    total = qs.count()
    generated = qs.filter(invitation_generated=True).count()
    sent = qs.filter(invitation_sent=True).count()
    present = qs.filter(places_used__gt=0).count()
    return {
        "total": total,
        "generated": generated,
        "sent": sent,
        "present": present,
    }


def dashboard_stats() -> dict:
    total = Invitation.objects.count()
    validated = Invitation.objects.filter(places_used__gt=0).count()
    remaining = total - validated
    places_expected = Invitation.objects.aggregate(total=Sum("places"))["total"] or 0
    places_admitted = (
        Invitation.objects.aggregate(total=Sum("places_used"))["total"] or 0
    )
    rate = (
        round((places_admitted / places_expected) * 100, 1) if places_expected else 0.0
    )
    recent = (
        Admission.objects.filter(is_cancelled=False)
        .select_related("invitation")[:30]
    )

    # Last 7 days admissions chart (Zanalyze-style bars)
    today = timezone.localdate()
    day_counts: list[dict] = []
    max_n = 1
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        n = Admission.objects.filter(
            is_cancelled=False,
            admitted_at__date=day,
        ).count()
        max_n = max(max_n, n)
        day_counts.append({"label": day.strftime("%d/%m"), "n": n, "date": day})
    for row in day_counts:
        row["pct"] = max(4, int(round((row["n"] / max_n) * 100))) if max_n else 4

    return {
        "total": total,
        "validated": validated,
        "remaining": remaining,
        "places_expected": places_expected,
        "places_admitted": places_admitted,
        "places_remaining": max(0, places_expected - places_admitted),
        "presence_rate": rate,
        "recent_scans": recent,
        "recipients": _type_stats(PARTICIPANT_RECIPIENT),
        "vips": _type_stats(PARTICIPANT_VIP),
        "admissions_chart": day_counts,
    }


def export_attendance_workbook() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Présence"
    ws.append(
        [
            "Code",
            "Nom",
            "Prénom",
            "Type",
            "Catégorie",
            "Places",
            "Places utilisées",
            "Présent",
            "Heure première entrée",
        ]
    )
    for inv in Invitation.objects.order_by("last_name", "first_name"):
        validated_at = ""
        if inv.validated_at:
            validated_at = timezone.localtime(inv.validated_at).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ws.append(
            [
                inv.code,
                inv.last_name,
                inv.first_name,
                inv.get_participant_type_display(),
                inv.category,
                inv.places,
                inv.places_used,
                "Oui" if inv.places_used > 0 else "Non",
                validated_at,
            ]
        )
    return wb


def export_attendance_response(filename: str = "rapport_presence.xlsx") -> HttpResponse:
    wb = export_attendance_workbook()
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
