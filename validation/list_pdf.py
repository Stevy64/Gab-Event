"""Liste d'invitations en PDF cérémoniel (thème crème / or de l'événement)."""
from __future__ import annotations

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
    _typeface,
)
from .constants import ceremony_settings
from .models import Event, Invitation

PAGE_W, PAGE_H = 1240, 1754
ROWS_PER_PAGE = 22
ROW_H = 48
MARGIN = 64


def _hex_rgb(value: str | None) -> tuple[int, int, int]:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 6:
        try:
            return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return GOLD


def _blend(a, b, t: float):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def export_guest_list_pdf_bytes(event: Event) -> bytes:
    cfg = ceremony_settings(event)
    accent = _hex_rgb(cfg.get("primary_color"))
    if sum(accent) < 90:
        accent = GOLD
    guests = list(
        Invitation.objects.filter(event=event)
        .order_by("last_name", "first_name", "id")
    )
    total = len(guests)
    pages_n = max(1, (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE) if total else 1
    encoded = []
    if not guests:
        encoded.append(_encode_page(_draw_list_page(event, cfg, accent, [], 1, 1, 0, 0)))
    else:
        for index in range(pages_n):
            chunk = guests[index * ROWS_PER_PAGE : (index + 1) * ROWS_PER_PAGE]
            start = index * ROWS_PER_PAGE
            page = _draw_list_page(
                event, cfg, accent, chunk, index + 1, pages_n, start, total
            )
            encoded.append(_encode_page(page))
    return _jpegs_to_pdf(encoded)


def export_guest_list_pdf_response(event: Event) -> HttpResponse:
    data = export_guest_list_pdf_bytes(event)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="liste_{event.slug}.pdf"'
    return response


def _encode_page(image: Image.Image) -> tuple[bytes, int, int]:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue(), image.width, image.height


def _draw_list_page(event, cfg, accent, rows, page_no, pages_n, start_index, total) -> Image.Image:
    img = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, PAGE_W, 10], fill=accent)
    draw.rectangle([MARGIN - 18, MARGIN - 18, PAGE_W - MARGIN + 18, PAGE_H - MARGIN + 18], outline=accent, width=2)
    draw.rectangle(
        [MARGIN - 8, MARGIN - 8, PAGE_W - MARGIN + 8, PAGE_H - MARGIN + 8],
        outline=GOLD_DEEP,
        width=1,
    )

    y = MARGIN + 8
    kicker = (cfg.get("subtitle") or "Gab Event").upper()
    kfont = _display(15)
    draw.text(((PAGE_W - _text_width(draw, kicker, kfont)) / 2, y), kicker, font=kfont, fill=accent)
    y += 36

    title = cfg.get("title") or event.name
    tfont = _typeface("Cinzel-Regular.ttf", 34, bold=True)
    for line in _fit_center(draw, title, tfont, PAGE_W - 2 * MARGIN):
        draw.text(((PAGE_W - _text_width(draw, line, tfont)) / 2, y), line, font=tfont, fill=INK)
        y += 42

    meta = "  ·  ".join(part for part in (cfg.get("date"), cfg.get("time"), cfg.get("venue")) if part)
    mfont = _serif(22)
    draw.text(((PAGE_W - _text_width(draw, meta, mfont)) / 2, y), meta, font=mfont, fill=NAVY)
    y += 40
    _rule(draw, PAGE_W // 2, y, accent, 280)
    y += 28

    head = _display(16)
    heading = "LISTE DES INVITATIONS"
    draw.text(((PAGE_W - _text_width(draw, heading, head)) / 2, y), heading, font=head, fill=accent)
    y += 30
    count_txt = f"{total} invité(s)"
    cfont = _serif(18, italic=True)
    draw.text(((PAGE_W - _text_width(draw, count_txt, cfont)) / 2, y), count_txt, font=cfont, fill=MUTED)
    y += 36

    cols = [
        (MARGIN + 8, 70, "N°"),
        (MARGIN + 78, 210, "CODE"),
        (MARGIN + 300, 430, "NOM"),
        (MARGIN + 740, 130, "TYPE"),
        (MARGIN + 880, 110, "PLACES"),
        (MARGIN + 1000, 140, "PRÉSENT"),
    ]
    header_top = y
    draw.rounded_rectangle(
        [MARGIN, header_top, PAGE_W - MARGIN, header_top + 42],
        radius=8,
        fill=_blend(accent, PAPER, 0.82),
    )
    hfont = _display(12)
    for x, _w, label in cols:
        draw.text((x, header_top + 12), label, font=hfont, fill=GOLD_DEEP)
    y = header_top + 50

    name_font = _serif(20, semibold=True)
    cell_font = _serif(18)
    small = _display(12)
    today = timezone.localdate().strftime("%d/%m/%Y")

    for offset, inv in enumerate(rows):
        top = y + offset * ROW_H
        if offset % 2 == 0:
            draw.rectangle([MARGIN, top, PAGE_W - MARGIN, top + ROW_H - 4], fill=PAPER_INNER)
        if inv.is_vip:
            draw.rectangle([MARGIN, top + 8, MARGIN + 5, top + ROW_H - 12], fill=accent)
        values = [
            (cols[0][0], f"{start_index + offset + 1:03d}", cell_font, MUTED),
            (cols[1][0], inv.code, small, INK),
            (cols[2][0], (inv.full_name or "—")[:32], name_font, INK),
            (cols[3][0], "VIP" if inv.is_vip else "Invité", small, accent if inv.is_vip else MUTED),
            (cols[4][0], f"{inv.places_used}/{inv.places}", cell_font, NAVY),
            (cols[5][0], "Oui" if inv.places_used else "Non", cell_font, NAVY if inv.places_used else MUTED),
        ]
        for x, text, font, fill in values:
            draw.text((x, top + 12), text, font=font, fill=fill)

    foot = f"GAB EVENT  ·  {today}  ·  {page_no}/{pages_n}"
    ffont = _display(12)
    draw.text(
        ((PAGE_W - _text_width(draw, foot, ffont)) / 2, PAGE_H - MARGIN - 8),
        foot,
        font=ffont,
        fill=accent,
    )
    return img


def _rule(draw, cx, y, color, width):
    draw.line([(cx - width // 2, y), (cx + width // 2, y)], fill=color, width=2)
    draw.ellipse([cx - 4, y - 4, cx + 4, y + 4], fill=color)


def _fit_center(draw, text, font, max_width):
    words = (text or "").split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:3]
