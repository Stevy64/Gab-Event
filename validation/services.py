"""
Logique métier : import Excel, lookup, admission atomique, stats, export.

Règle importante :
  - ``lookup_invitation`` identifie sans consommer de places
  - ``admit_persons`` consomme N places sous transaction / select_for_update
  - Toute mutation utilisateur est limitée au contexte Event / owner
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from .code_service import generate_invitation_code, normalize_code
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Admission, Event, Invitation, ScanLog
from .quota_service import can_add_invitations, quota_status

__all__ = [
    "normalize_code",
    "import_invitations_from_workbook",
    "import_invitations_from_path",
    "analyze_import_workbook",
    "lookup_invitation",
    "validate_invitation",
    "admit_persons",
    "cancel_validation",
    "dashboard_stats",
    "event_dashboard_stats",
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
        "STANDARD": PARTICIPANT_RECIPIENT,
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
    refused: bool = False
    refusal_message: str = ""

    @property
    def imported(self) -> int:
        return self.created + self.updated


@dataclass
class ImportAnalysis:
    new_regular: int = 0
    new_vip: int = 0
    updates: int = 0
    errors: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)


def _parse_workbook_rows(workbook) -> tuple[list[dict], list[str]]:
    """Parse rows into normalized dicts + header errors."""
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    errors: list[str] = []
    if not rows:
        return [], ["Le fichier Excel est vide."]

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    header_map = {h.lower(): idx for idx, h in enumerate(headers) if h}
    has_prenom = "prenom" in header_map or "prénom" in header_map
    if "nom" not in header_map or not has_prenom:
        return [], [
            "Colonnes manquantes : Nom, Prenom. "
            "Optionnelles : Code, Type, Categorie, Places, Statut."
        ]

    parsed: list[dict] = []
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
            errors.append(f"Ligne {line_no} : nom ou prénom manquant.")
            continue
        try:
            places = 1
            if places_raw not in ("", None):
                int(float(places_raw))
        except (TypeError, ValueError):
            errors.append(f"Ligne {line_no} : places invalides ({places_raw!r}).")
            continue

        if not category:
            category = "Standard" if participant_type == PARTICIPANT_RECIPIENT else "VIP"

        parsed.append(
            {
                "line_no": line_no,
                "last_name": last_name,
                "first_name": first_name,
                "category": category,
                "participant_type": participant_type,
                "places": places,
                "status": status,
                "code": code,
            }
        )
    return parsed, errors


def analyze_import_workbook(workbook, event: Event | None = None) -> ImportAnalysis:
    parsed, errors = _parse_workbook_rows(workbook)
    analysis = ImportAnalysis(errors=errors, rows=parsed)
    seen_codes: set[str] = set()
    for item in parsed:
        code = item["code"]
        existing = None
        if code:
            if code in seen_codes:
                analysis.errors.append(
                    f"Ligne {item['line_no']} : code en double dans le fichier ({code})."
                )
                continue
            seen_codes.add(code)
            qs = Invitation.objects.filter(code__iexact=code)
            if event is not None:
                qs = qs.filter(event=event)
            existing = qs.first()
        if existing:
            analysis.updates += 1
        elif item["participant_type"] == PARTICIPANT_VIP:
            analysis.new_vip += 1
        else:
            analysis.new_regular += 1
    return analysis


def import_invitations_from_workbook(
    workbook,
    event: Event | None = None,
    *,
    enforce_quotas: bool = True,
) -> ImportResult:
    """Import / upsert invitations. Never regenerates existing codes."""
    result = ImportResult()
    analysis = analyze_import_workbook(workbook, event=event)
    result.errors.extend(analysis.errors)

    if event is not None and enforce_quotas:
        check = can_add_invitations(
            event,
            regular_to_add=analysis.new_regular,
            vip_to_add=analysis.new_vip,
        )
        if not check.allowed:
            result.refused = True
            result.refusal_message = check.message + " Voir les autres formules."
            result.errors.insert(0, result.refusal_message)
            return result

    seen_codes: set[str] = set()
    for item in analysis.rows:
        code = item["code"]
        existing = None
        if code:
            if code in seen_codes:
                continue
            qs = Invitation.objects.filter(code__iexact=code)
            if event is not None:
                # Autoriser match global pour ré-associer legacy au même code
                existing = Invitation.objects.filter(code__iexact=code).first()
                if existing and existing.event_id and existing.event_id != event.id:
                    result.errors.append(
                        f"Ligne {item['line_no']} : code déjà utilisé par un autre événement ({code})."
                    )
                    continue
            else:
                existing = qs.first()

        if existing:
            if event is not None and existing.event_id is None:
                existing.event = event
            existing.last_name = item["last_name"]
            existing.first_name = item["first_name"]
            existing.category = item["category"]
            existing.participant_type = item["participant_type"]
            existing.places = item["places"]
            existing.status = item["status"]
            existing.imported_at = timezone.now()
            update_fields = [
                "last_name",
                "first_name",
                "category",
                "participant_type",
                "places",
                "status",
                "imported_at",
            ]
            if event is not None:
                update_fields.append("event")
            existing.save(update_fields=update_fields)
            seen_codes.add(existing.code)
            result.updated += 1
            continue

        if not code:
            code = generate_invitation_code(item["participant_type"], event=event)
        elif Invitation.objects.filter(code__iexact=code).exists():
            result.errors.append(
                f"Ligne {item['line_no']} : code déjà utilisé ({code})."
            )
            continue

        if code in seen_codes:
            result.errors.append(f"Ligne {item['line_no']} : code en double ({code}).")
            continue
        seen_codes.add(code)

        Invitation.objects.create(
            event=event,
            code=code,
            last_name=item["last_name"],
            first_name=item["first_name"],
            category=item["category"],
            participant_type=item["participant_type"],
            places=item["places"],
            status=item["status"],
        )
        result.created += 1

    return result


def import_invitations_from_path(
    path: str | Path,
    event: Event | None = None,
    *,
    enforce_quotas: bool = True,
) -> ImportResult:
    path = Path(path)
    if not path.exists():
        result = ImportResult()
        result.errors.append(f"Fichier introuvable : {path}")
        return result
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return import_invitations_from_workbook(
            workbook, event=event, enforce_quotas=enforce_quotas
        )
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
        "event_id": invitation.event_id,
    }


@dataclass
class LookupResult:
    status: str
    guest: dict | None = None
    validated_at: datetime | None = None
    invitation: Invitation | None = None
    message: str = ""

    def to_dict(self) -> dict:
        payload = {"status": self.status}
        if self.guest is not None:
            payload["guest"] = self.guest
        if self.validated_at is not None:
            payload["validated_at"] = self.validated_at.isoformat()
        if self.message:
            payload["message"] = self.message
        return payload


def lookup_invitation(
    code: str,
    agent: str = "",
    event: Event | None = None,
) -> LookupResult:
    """
    Identify an invitation without consuming places.
    Statuses: recognized | already_used | invalid | wrong_event
    Si ``event`` est fourni, le code doit appartenir à cet événement.
    """
    if event is not None and event.needs_payment:
        return LookupResult(
            status="invalid",
            message="Paiement non finalisé : le scan est indisponible.",
        )
    normalized = normalize_code(code)
    if not normalized:
        ScanLog.objects.create(
            invitation=None,
            event=event,
            code_scanned=code or "",
            result=ScanLog.RESULT_INVALID,
            agent=agent,
        )
        return LookupResult(status="invalid", message="Code vide ou illisible.")

    qs = Invitation.objects.select_related("event")
    if event is not None:
        qs = qs.filter(event=event)
    invitation = qs.filter(code__iexact=normalized).first()
    if invitation is None:
        # Code valide ailleurs → refus contextualisé
        if event is not None:
            other = (
                Invitation.objects.select_related("event")
                .filter(code__iexact=normalized)
                .exclude(event=event)
                .first()
            )
            if other is not None:
                ScanLog.objects.create(
                    invitation=other,
                    event=event,
                    code_scanned=normalized,
                    result=ScanLog.RESULT_INVALID,
                    agent=agent,
                )
                other_name = other.event.name if other.event_id else "un autre événement"
                return LookupResult(
                    status="wrong_event",
                    message=(
                        f"Cette invitation appartient à « {other_name} », "
                        f"pas à « {event.name} »."
                    ),
                )
        ScanLog.objects.create(
            invitation=None,
            event=event,
            code_scanned=normalized,
            result=ScanLog.RESULT_INVALID,
            agent=agent,
        )
        return LookupResult(
            status="invalid",
            message="Ce QR Code ne correspond à aucune invitation valide.",
        )

    Invitation.objects.filter(pk=invitation.pk).update(scan_count=F("scan_count") + 1)
    invitation.refresh_from_db(fields=["scan_count"])

    if not invitation.is_active_ticket:
        ScanLog.objects.create(
            invitation=invitation,
            event=invitation.event,
            code_scanned=normalized,
            result=ScanLog.RESULT_DISABLED,
            agent=agent,
        )
        return LookupResult(status="invalid", message="Invitation désactivée.")

    if invitation.is_exhausted:
        ScanLog.objects.create(
            invitation=invitation,
            event=invitation.event,
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
        event=invitation.event,
        code_scanned=normalized,
        result=ScanLog.RESULT_RECOGNIZED,
        agent=agent,
    )
    return LookupResult(
        status="recognized",
        guest=guest_payload(invitation),
        invitation=invitation,
    )


def validate_invitation(code: str, agent: str = "", event: Event | None = None) -> LookupResult:
    return lookup_invitation(code, agent=agent, event=event)


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


def admit_persons(
    code: str,
    persons: int = 1,
    agent: str = "",
    event: Event | None = None,
) -> AdmitResult:
    """Enregistre l'entrée d'une seule personne (1 invitation = 1 billet = 1 entrée)."""
    if event is not None and event.needs_payment:
        return AdmitResult(
            status="error",
            message="Paiement non finalisé : aucune entrée n’est possible.",
        )
    normalized = normalize_code(code)
    persons = 1

    if not normalized:
        return AdmitResult(status="invalid", message="Code vide ou illisible.")

    with transaction.atomic():
        # Pas de select_related ici : event est nullable, Postgres refuse
        # FOR UPDATE sur le côté optionnel d'un LEFT OUTER JOIN.
        qs = Invitation.objects.select_for_update()
        if event is not None:
            qs = qs.filter(event=event)
        invitation = qs.filter(code__iexact=normalized).first()
        if invitation is None:
            if event is not None:
                other = (
                    Invitation.objects.filter(code__iexact=normalized)
                    .exclude(event=event)
                    .select_related("event")
                    .first()
                )
                if other is not None:
                    other_name = other.event.name if other.event_id else "un autre événement"
                    return AdmitResult(
                        status="wrong_event",
                        message=(
                            f"Cette invitation appartient à « {other_name} », "
                            f"pas à « {event.name} »."
                        ),
                    )
            return AdmitResult(status="invalid", message="Invitation introuvable.")

        if not invitation.is_active_ticket:
            return AdmitResult(status="invalid", message="Invitation désactivée.")

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
            event=invitation.event,
            persons=1,
            admitted_at=now,
            agent=agent,
        )
        ScanLog.objects.create(
            invitation=invitation,
            event=invitation.event,
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


def search_invitations(query: str, event: Event | None = None):
    query = (query or "").strip()
    qs = Invitation.objects.all()
    if event is not None:
        qs = qs.filter(event=event)
    if not query:
        return qs.none()
    return qs.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(code__icontains=normalize_code(query))
        | Q(category__icontains=query)
    )


def _type_stats(participant_type: str, event: Event | None = None) -> dict:
    qs = Invitation.objects.filter(participant_type=participant_type)
    if event is not None:
        qs = qs.filter(event=event)
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


def presence_tone(rate) -> str:
    """Couleur du compteur : rouge <20 %, orange ≤50 %, bleu ≤90 %, vert >90 %."""
    try:
        n = float(rate or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n < 20:
        return "red"
    if n <= 50:
        return "orange"
    if n <= 90:
        return "blue"
    return "green"


def event_dashboard_stats(event: Event) -> dict:
    qs = Invitation.objects.filter(event=event)
    total = qs.count()
    validated = qs.filter(places_used__gt=0).count()
    remaining = total - validated
    places_expected = qs.aggregate(total=Sum("places"))["total"] or 0
    places_admitted = qs.aggregate(total=Sum("places_used"))["total"] or 0
    rate = (
        round((places_admitted / places_expected) * 100, 1) if places_expected else 0.0
    )
    recent = (
        Admission.objects.filter(is_cancelled=False, event=event)
        .select_related("invitation")[:30]
    )
    today = timezone.localdate()
    day_counts: list[dict] = []
    max_n = 1
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        n = Admission.objects.filter(
            is_cancelled=False,
            event=event,
            admitted_at__date=day,
        ).count()
        max_n = max(max_n, n)
        day_counts.append({"label": day.strftime("%d/%m"), "n": n, "date": day})
    for row in day_counts:
        row["pct"] = max(4, int(round((row["n"] / max_n) * 100))) if max_n else 4

    quotas = quota_status(event)
    return {
        "total": total,
        "validated": validated,
        "remaining": remaining,
        "places_expected": places_expected,
        "places_admitted": places_admitted,
        "places_remaining": max(0, places_expected - places_admitted),
        "presence_rate": rate,
        "presence_tone": presence_tone(rate),
        "recent_scans": recent,
        "recipients": _type_stats(PARTICIPANT_RECIPIENT, event),
        "vips": _type_stats(PARTICIPANT_VIP, event),
        "admissions_chart": day_counts,
        "quotas": quotas,
        "sent": qs.filter(invitation_sent=True).count(),
    }


def dashboard_stats(event: Event | None = None) -> dict:
    if event is not None:
        return event_dashboard_stats(event)
    # Agrégat global (platform-admin / legacy)
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
        "presence_tone": presence_tone(rate),
        "recent_scans": recent,
        "recipients": _type_stats(PARTICIPANT_RECIPIENT),
        "vips": _type_stats(PARTICIPANT_VIP),
        "admissions_chart": day_counts,
    }


def export_attendance_workbook(event: Event | None = None) -> Workbook:
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
            "E-mail",
            "Téléphone",
            "Source",
            "Places",
            "Places utilisées",
            "Présent",
            "Heure première entrée",
            "Paiement",
            "Montant",
        ]
    )
    qs = Invitation.objects.select_related("guest_payment").order_by(
        "last_name", "first_name"
    )
    if event is not None:
        qs = qs.filter(event=event)
    for inv in qs:
        validated_at = ""
        if inv.validated_at:
            validated_at = timezone.localtime(inv.validated_at).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        pay = None
        try:
            pay = inv.guest_payment
        except Exception:
            pay = None
        ws.append(
            [
                inv.code,
                inv.last_name,
                inv.first_name,
                inv.get_participant_type_display(),
                inv.category,
                getattr(inv, "email", "") or "",
                getattr(inv, "phone", "") or "",
                inv.get_source_display() if hasattr(inv, "get_source_display") else "",
                inv.places,
                inv.places_used,
                "Oui" if inv.places_used > 0 else "Non",
                validated_at,
                pay.get_status_display() if pay else ("Gratuit" if getattr(inv, "source", "") == "form" else "—"),
                f"{pay.amount} {pay.currency}" if pay else "",
            ]
        )
    return wb


def export_attendance_response(
    filename: str = "rapport_presence.xlsx",
    event: Event | None = None,
) -> HttpResponse:
    wb = export_attendance_workbook(event=event)
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
