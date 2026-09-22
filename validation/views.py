"""
Vues HTTP — pages publiques, API scan/admission, espace admin.

API (CSRF requis) :
  POST /api/validate/  → lookup (ne consomme pas de places)
  POST /api/admit/     → enregistre N entrées atomiquement
"""
from __future__ import annotations

import json
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from openpyxl import load_workbook

from .card_service import (
    build_invitations_zip,
    generate_invitation_card,
    invitation_filename,
)
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP, ceremony_settings
from .forms import CancelValidationForm, ExcelImportForm, InvitationSearchForm
from .models import Admission, Invitation
from .qr_service import generate_invitation_qr, qr_png_bytes
from .services import (
    admit_persons,
    cancel_validation,
    dashboard_stats,
    export_attendance_response,
    import_invitations_from_workbook,
    lookup_invitation,
    mark_invitation_sent,
    search_invitations,
)


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _agent(request) -> str:
    if request.user.is_authenticated:
        return request.user.get_username()
    return ""


def _require_scanner_user(request):
    """Seuls les comptes connectés (contrôleurs / admin) peuvent scanner."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "status": "error",
                "message": "Connectez-vous pour scanner les invitations.",
            },
            status=401,
        )
    return None


@ensure_csrf_cookie
def home(request):
    can_scan = request.user.is_authenticated
    open_scanner = can_scan and request.GET.get("scan") == "1"
    return render(
        request,
        "home.html",
        {
            "open_scanner": open_scanner,
            "can_scan": can_scan,
            "ceremony": ceremony_settings(),
        },
    )


@require_GET
def service_worker(request):
    path = settings.BASE_DIR / "static" / "sw.js"
    response = FileResponse(path.open("rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_required
@ensure_csrf_cookie
def scanner(request):
    return redirect("/?scan=1")


@require_POST
def api_validate(request):
    """Lookup invitation — does NOT consume places. Auth required."""
    denied = _require_scanner_user(request)
    if denied:
        return denied
    content_type = request.content_type or ""
    if "application/json" in content_type:
        payload = _parse_json(request)
        if payload is None:
            return JsonResponse({"status": "error", "message": "JSON invalide."}, status=400)
        code = payload.get("code", "")
    else:
        code = request.POST.get("code", "")

    result = lookup_invitation(code, agent=_agent(request))
    status_code = 200 if result.status != "invalid" else 404
    return JsonResponse(result.to_dict(), status=status_code)


@require_POST
def api_admit(request):
    """Confirm entrance (1 personne). Auth required."""
    denied = _require_scanner_user(request)
    if denied:
        return denied
    payload = _parse_json(request) if "application/json" in (request.content_type or "") else None
    if payload is None and "application/json" in (request.content_type or ""):
        return JsonResponse({"status": "error", "message": "JSON invalide."}, status=400)
    if payload is None:
        payload = {
            "code": request.POST.get("code", ""),
            "persons": request.POST.get("persons", 1),
        }

    result = admit_persons(
        payload.get("code", ""),
        1,
        agent=_agent(request),
    )
    http = 200
    if result.status == "invalid":
        http = 404
    elif result.status == "error":
        http = 400
    elif result.status == "already_used":
        http = 409
    return JsonResponse(result.to_dict(), status=http)


@login_required
@require_GET
def dashboard(request):
    form = InvitationSearchForm(request.GET or None)
    stats = dashboard_stats()
    type_filter = request.GET.get("type", "all")
    status_filter = request.GET.get("status", "all")
    qs = Invitation.objects.all()
    if type_filter == "RECIPIENT":
        qs = qs.filter(participant_type=PARTICIPANT_RECIPIENT)
    elif type_filter == "VIP":
        qs = qs.filter(participant_type=PARTICIPANT_VIP)

    if status_filter == "todo":
        qs = qs.filter(invitation_generated=False)
    elif status_filter == "tosend":
        qs = qs.filter(invitation_generated=True, invitation_sent=False, places_used=0)
    elif status_filter == "sent":
        qs = qs.filter(invitation_sent=True)
    elif status_filter == "present":
        qs = qs.filter(places_used__gt=0)
    elif status_filter == "pending":
        qs = qs.filter(places_used=0)

    query = ""
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        if query:
            qs = search_invitations(query)

    guests = list(qs[:100])
    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "form": form,
            "guests": guests,
            "query": query,
            "type_filter": type_filter,
            "status_filter": status_filter,
            "ceremony": ceremony_settings(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def import_excel(request):
    form = ExcelImportForm()
    import_result = None
    if request.method == "POST":
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            try:
                workbook = load_workbook(uploaded, read_only=True, data_only=True)
                import_result = import_invitations_from_workbook(workbook)
                workbook.close()
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f"Impossible de lire le fichier : {exc}")
            else:
                if import_result.errors:
                    for err in import_result.errors[:20]:
                        messages.warning(request, err)
                if import_result.imported:
                    messages.success(
                        request,
                        f"{import_result.imported} ligne(s) traitée(s) "
                        f"({import_result.created} créée(s), "
                        f"{import_result.updated} mise(s) à jour).",
                    )
                elif not import_result.errors:
                    messages.info(request, "Aucune ligne à importer.")
    return render(request, "import.html", {"form": form, "import_result": import_result})


@login_required
@require_GET
def export_report(request):
    return export_attendance_response()


@login_required
@require_http_methods(["GET", "POST"])
def invitation_detail(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    form = CancelValidationForm()
    if request.method == "POST":
        action = request.POST.get("action", "cancel")
        if action == "mark_sent":
            mark_invitation_sent(invitation, True)
            messages.success(request, "Invitation marquée comme envoyée.")
            return redirect("invitation_detail", pk=invitation.pk)
        if action == "unmark_sent":
            mark_invitation_sent(invitation, False)
            messages.success(request, "Statut « envoyée » annulé.")
            return redirect("invitation_detail", pk=invitation.pk)
        form = CancelValidationForm(request.POST)
        if form.is_valid() and invitation.places_used > 0:
            cancel_validation(invitation)
            messages.success(request, f"Entrées annulées pour {invitation.full_name}.")
            return redirect("invitation_detail", pk=invitation.pk)
    logs = invitation.scan_logs.all()[:20]
    admissions = invitation.admissions.filter(is_cancelled=False)[:20]
    return render(
        request,
        "invitation_detail.html",
        {
            "invitation": invitation,
            "form": form,
            "logs": logs,
            "admissions": admissions,
            "ceremony": ceremony_settings(),
        },
    )


@login_required
@require_GET
def invitation_preview(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    return render(
        request,
        "invitation_preview.html",
        {"invitation": invitation, "ceremony": ceremony_settings()},
    )


@login_required
@require_GET
def invitation_download(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    generate_invitation_qr(invitation)
    data, _ = generate_invitation_card(invitation, save=True)
    response = HttpResponse(data, content_type="image/png")
    if request.GET.get("inline") != "1":
        response["Content-Disposition"] = (
            f'attachment; filename="{invitation_filename(invitation)}"'
        )
    return response


@login_required
@require_GET
def invitation_qr_download(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    data = qr_png_bytes(invitation.code)
    response = HttpResponse(data, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{invitation.code}.png"'
    return response


@login_required
@require_POST
def generate_all_invitations(request):
    only_missing = request.POST.get("only_missing") == "1"
    type_filter = request.POST.get("type") or None
    qs = Invitation.objects.all()
    if type_filter in (PARTICIPANT_RECIPIENT, PARTICIPANT_VIP):
        qs = qs.filter(participant_type=type_filter)
    data, summary = build_invitations_zip(qs, only_missing=only_missing)
    for inv in qs.iterator():
        generate_invitation_qr(inv)
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = (
        'attachment; filename="invitations_ceremonie.zip"'
    )
    messages.success(
        request,
        f"Génération : {summary['generated']} créée(s), "
        f"{summary['skipped']} existante(s), {summary['errors']} erreur(s).",
    )
    return response


@login_required
@require_GET
def search_page(request):
    form = InvitationSearchForm(request.GET or None)
    results = []
    query = ""
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        if query:
            results = list(search_invitations(query)[:50])
    return render(
        request,
        "search.html",
        {"form": form, "results": results, "query": query},
    )
