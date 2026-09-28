"""Facture PDF professionnelle (NIF / RCCM) pour les entreprises gabonaises."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from PIL import Image, ImageDraw

from .card_service import (
    GOLD,
    GOLD_DEEP,
    INK,
    MUTED,
    NAVY,
    PAPER,
    PAPER_INNER,
    _display,
    _jpegs_to_pdf,
    _serif,
    _text_width,
)
from .models import GuestPayment, Payment, SiteSettings

PAGE_W, PAGE_H = 1240, 1754
MARGIN = 64
RADIUS = 18


def _money(value) -> str:
    amount = Decimal(value or 0).quantize(Decimal("1"))
    return f"{int(amount):,}".replace(",", " ") + " F CFA"


def _legal(site: SiteSettings) -> dict:
    return {
        "name": (site.legal_company_name or site.site_name or "Gab Event").strip(),
        "nif": (site.legal_nif or "").strip() or "—",
        "rccm": (site.legal_rccm or "").strip() or "—",
        "address": (site.legal_address or "").strip(),
        "city": (site.legal_city or "Libreville").strip(),
        "phone": (site.legal_phone or site.support_phone or "").strip(),
        "email": (site.legal_email or site.support_email or "").strip(),
        "policy": site.payout_policy_text(),
    }


def _wrap(text: str, width: int) -> list[str]:
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) > width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [""]


def _round_rect(draw: ImageDraw.ImageDraw, box, radius: int, *, fill=None, outline=None, width: int = 1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_invoice(
    title: str,
    number: str,
    client_lines: list[str],
    rows: list[tuple[str, str]],
    totals: list[tuple[str, str, bool]],
    footer: str,
) -> bytes:
    site = SiteSettings.load()
    legal = _legal(site)
    issued = timezone.localtime()
    img = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(img)

    # Soft page frame
    _round_rect(
        draw,
        (28, 28, PAGE_W - 28, PAGE_H - 28),
        28,
        outline=(226, 218, 204),
        width=2,
    )

    # Header band
    _round_rect(draw, (MARGIN - 8, 52, PAGE_W - MARGIN + 8, 220), RADIUS + 4, fill=NAVY)
    brand = _serif(40, semibold=True)
    draw.text((MARGIN + 18, 72), legal["name"].upper(), font=brand, fill=GOLD)
    kicker = _display(16)
    draw.text((MARGIN + 18, 128), "FACTURE", font=kicker, fill=PAPER)
    meta = _serif(18)
    draw.text((MARGIN + 18, 164), f"N° {number}", font=meta, fill=PAPER_INNER)
    date_txt = issued.strftime("%d/%m/%Y")
    dw = _text_width(draw, date_txt, meta)
    draw.text((PAGE_W - MARGIN - 26 - dw, 164), date_txt, font=meta, fill=PAPER_INNER)

    y = 252
    # Seller / client cards side by side
    mid = PAGE_W // 2
    gap = 18
    left_box = (MARGIN, y, mid - gap // 2, y + 210)
    right_box = (mid + gap // 2, y, PAGE_W - MARGIN, y + 210)
    _round_rect(draw, left_box, RADIUS, fill=PAPER_INNER, outline=(228, 220, 206), width=1)
    _round_rect(draw, right_box, RADIUS, fill=PAPER_INNER, outline=(228, 220, 206), width=1)

    label_font = _display(12)
    body = _serif(17)
    muted_font = _serif(15)

    draw.text((MARGIN + 22, y + 18), "ÉMETTEUR", font=label_font, fill=GOLD_DEEP)
    seller_y = y + 48
    seller_lines = [
        legal["name"],
        f"NIF {legal['nif']}  ·  RCCM {legal['rccm']}",
        legal["address"],
        legal["city"],
        " · ".join(part for part in (legal["phone"], legal["email"]) if part),
    ]
    for line in seller_lines:
        if not line:
            continue
        draw.text((MARGIN + 22, seller_y), line[:48], font=muted_font if seller_y > y + 48 else body, fill=INK if seller_y == y + 48 else MUTED)
        seller_y += 28

    draw.text((mid + gap // 2 + 22, y + 18), "FACTURÉ À", font=label_font, fill=GOLD_DEEP)
    client_y = y + 48
    for line in client_lines:
        if not line:
            continue
        draw.text((mid + gap // 2 + 22, client_y), str(line)[:42], font=body if client_y == y + 48 else muted_font, fill=INK if client_y == y + 48 else MUTED)
        client_y += 30

    y += 236
    title_font = _serif(26, semibold=True)
    draw.text((MARGIN, y), title, font=title_font, fill=INK)
    y += 48

    # Table header
    table_top = y
    _round_rect(
        draw,
        (MARGIN, table_top, PAGE_W - MARGIN, table_top + 52),
        14,
        fill=NAVY,
    )
    head = _display(13)
    draw.text((MARGIN + 24, table_top + 16), "Désignation", font=head, fill=PAPER)
    hw = _text_width(draw, "Montant", head)
    draw.text((PAGE_W - MARGIN - 24 - hw, table_top + 16), "Montant", font=head, fill=PAPER)
    y = table_top + 60

    row_font = _serif(17)
    for index, (label, amount) in enumerate(rows):
        fill = PAPER_INNER if index % 2 == 0 else (255, 255, 255)
        _round_rect(
            draw,
            (MARGIN, y, PAGE_W - MARGIN, y + 56),
            12,
            fill=fill,
            outline=(232, 224, 210),
            width=1,
        )
        draw.text((MARGIN + 24, y + 16), label[:62], font=row_font, fill=INK)
        aw = _text_width(draw, amount, row_font)
        draw.text((PAGE_W - MARGIN - 24 - aw, y + 16), amount, font=row_font, fill=INK)
        y += 64

    y += 12
    totals_box_h = 28 + len(totals) * 42
    _round_rect(
        draw,
        (PAGE_W // 2, y, PAGE_W - MARGIN, y + totals_box_h),
        RADIUS,
        fill=PAPER_INNER,
        outline=(228, 220, 206),
        width=1,
    )
    ty = y + 18
    for label, amount, strong in totals:
        font = _serif(21, semibold=True) if strong else _serif(16)
        color = NAVY if strong else MUTED
        draw.text((PAGE_W // 2 + 22, ty), label, font=font, fill=color)
        aw = _text_width(draw, amount, font)
        draw.text((PAGE_W - MARGIN - 22 - aw, ty), amount, font=font, fill=color)
        ty += 40 if strong else 34

    y += totals_box_h + 36
    _round_rect(
        draw,
        (MARGIN, y, PAGE_W - MARGIN, y + 168),
        RADIUS,
        fill=(255, 252, 246),
        outline=(232, 220, 196),
        width=1,
    )
    draw.text((MARGIN + 22, y + 18), "CONDITIONS", font=label_font, fill=GOLD_DEEP)
    note = _serif(15)
    ny = y + 48
    for chunk in _wrap(footer, 78)[:4]:
        draw.text((MARGIN + 22, ny), chunk, font=note, fill=MUTED)
        ny += 26

    draw.text(
        (MARGIN, PAGE_H - 72),
        "Document généré par Gab Event — facture valable pour comptabilité.",
        font=_serif(13),
        fill=MUTED,
    )
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=93)
    return _jpegs_to_pdf([(buf.getvalue(), PAGE_W, PAGE_H)])


def guest_payment_invoice_bytes(payment: GuestPayment) -> bytes:
    site = SiteSettings.load()
    number = f"GE-INV-{payment.pk:06d}"
    event = payment.event
    owner_name = ""
    if event and event.owner_id:
        owner_name = (event.owner.get_full_name() or event.owner.username or "").strip()
    client = [
        payment.full_name,
        payment.email or payment.phone,
        event.name if event else "",
        owner_name,
    ]
    kind = payment.get_participant_type_display()
    event_name = event.name if event else "Événement"
    rows = [(f"Invitation {kind} — {event_name}", _money(payment.amount))]
    totals = [
        ("Commission Gab Event", _money(payment.commission_amount), False),
        ("Net organisateur", _money(payment.net_amount), True),
    ]
    return _draw_invoice(
        "Facture invitation",
        number,
        client,
        rows,
        totals,
        site.payout_policy_text(),
    )


def event_payment_invoice_bytes(payment: Payment) -> bytes:
    number = f"GE-EVT-{payment.pk:06d}"
    owner = payment.user
    event = payment.event
    client = [
        ((owner.get_full_name() or owner.username) if owner else ""),
        getattr(owner, "email", "") or "",
        event.name if event else "",
        payment.plan.name if payment.plan_id else "",
    ]
    plan_name = payment.plan.name if payment.plan_id else "événement"
    rows = [(f"Formule {plan_name}", _money(payment.amount))]
    totals = [("Total TTC", _money(payment.amount), True)]
    return _draw_invoice(
        "Facture événement",
        number,
        client,
        rows,
        totals,
        "Paiement de la formule organisateur. Document destiné à la comptabilité de l’entreprise.",
    )


def invoice_response(data: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
