"""
Cartes d'invitation PNG (identité + QR + flyer événement) et archive ZIP.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .constants import ceremony_settings
from .models import Invitation
from .qr_service import build_qr_image

NAVY = (26, 39, 68)
NAVY_2 = (61, 79, 115)
ORANGE = (242, 101, 34)
WHITE = (255, 255, 255)
GOLD = (184, 148, 74)
GOLD_DEEP = (132, 100, 42)
MUTED = (92, 103, 128)
PAPER = (248, 242, 226)
PAPER_INNER = (255, 251, 240)
INK = (26, 39, 68)

FONTS_DIR = Path(__file__).resolve().parent / "fonts"


def _font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/georgia.ttf" if not bold else "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _typeface(filename: str, size: int, *, bold: bool = False):
    path = FONTS_DIR / filename
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return _font(size, bold=bold)


def _script(size: int):
    return _typeface("GreatVibes-Regular.ttf", size)


def _serif(size: int, *, italic: bool = False, semibold: bool = False):
    if italic:
        return _typeface("CormorantGaramond-Italic.ttf", size)
    if semibold:
        return _typeface("CormorantGaramond-SemiBold.ttf", size, bold=True)
    return _typeface("CormorantGaramond-Regular.ttf", size)


def _display(size: int):
    return _typeface("Cinzel-Regular.ttf", size, bold=True)


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", (value or "").strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "invite"


def invitation_pdf_filename(invitation: Invitation) -> str:
    return invitation_filename(invitation).removesuffix(".png") + ".pdf"


def invitation_pdf_bytes(png_data: bytes) -> bytes:
    """Enveloppe la carte PNG dans un PDF une page, sans dépendance extra."""
    image = Image.open(BytesIO(png_data)).convert("RGB")
    jpeg_buf = BytesIO()
    image.save(jpeg_buf, format="JPEG", quality=90)
    jpeg = jpeg_buf.getvalue()
    width, height = image.size
    return _jpeg_to_pdf(jpeg, width, height)


def _pdf_escape_length(n: int) -> bytes:
    return str(n).encode("ascii")


def _jpeg_to_pdf(jpeg: bytes, width: int, height: int) -> bytes:
    return _jpegs_to_pdf([(jpeg, width, height)])


def _jpegs_to_pdf(pages: list[tuple[bytes, int, int]]) -> bytes:
    """Assemble un PDF multi-pages à partir de JPEG (largeur, hauteur)."""
    if not pages:
        raise ValueError("PDF vide")
    kids = []
    objects: list[bytes] = [b"", b""]
    for index, (jpeg, width, height) in enumerate(pages):
        page_id = 3 + index * 3
        content_id = page_id + 1
        image_id = page_id + 2
        kids.append(f"{page_id} 0 R")
        content = f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ\n".encode("ascii")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                f"/Contents {content_id} 0 R /Resources << /XObject << /Im0 {image_id} 0 R >> >> >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length " + _pdf_escape_length(len(content)) + b" >>\nstream\n" + content + b"endstream"
        )
        objects.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(jpeg)} >>\nstream\n"
            ).encode("ascii")
            + jpeg
            + b"\nendstream"
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    ).encode("ascii")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def invitation_filename(invitation: Invitation) -> str:
    if invitation.is_vip:
        prefix = "VIP"
    elif invitation.event_id and invitation.event.code_prefix:
        prefix = invitation.event.code_prefix
    else:
        from .constants import RECIPIENT_CODE_PREFIX

        prefix = RECIPIENT_CODE_PREFIX
    return (
        f"invitation_{prefix}_"
        f"{safe_filename_part(invitation.first_name)}_"
        f"{safe_filename_part(invitation.last_name)}.png"
    )


def invitations_dir() -> Path:
    path = Path(settings.BASE_DIR) / "generated_invitations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hex_to_rgb(value: str, fallback=ORANGE):
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 6:
        try:
            return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return fallback
    return fallback


def _static_image(rel: str) -> Path | None:
    if not rel:
        return None
    cleaned = str(rel).replace("\\", "/").lstrip("/")
    if cleaned.startswith("static/"):
        cleaned = cleaned[7:]
    candidates = [
        Path(settings.BASE_DIR) / "static" / cleaned,
        Path(settings.BASE_DIR) / cleaned,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _cover_path(event) -> Path | None:
    if event is not None and getattr(event, "flyer", None):
        try:
            path = Path(event.flyer.path)
            if path.exists():
                return path
        except (ValueError, OSError):
            pass
    if event is not None:
        try:
            from .models import EventCategory

            cat = EventCategory.objects.filter(slug=event.event_type).first()
        except Exception:
            cat = None
        if cat:
            if cat.default_image:
                try:
                    path = Path(cat.default_image.path)
                    if path.exists():
                        return path
                except (ValueError, OSError):
                    pass
            static_cover = _static_image(cat.default_image_static)
            if static_cover:
                return static_cover
    from .branding import DEFAULT_COVER

    return _static_image(DEFAULT_COVER)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text or "", font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_font(draw: ImageDraw.ImageDraw, text: str, factory, start: int, min_size: int, max_width: int):
    size = start
    font = factory(size)
    while size > min_size and _text_width(draw, text, font) > max_width:
        size -= 3
        font = factory(size)
    return font


def _draw_corner(draw: ImageDraw.ImageDraw, x: int, y: int, dx: int, dy: int, color, scale: int = 58):
    draw.line([(x, y + dy * scale), (x, y), (x + dx * scale, y)], fill=color, width=3)
    x0, x1 = sorted((x + dx * 4, x + dx * 34))
    y0, y1 = sorted((y + dy * 4, y + dy * 34))
    start = { (1, 1): 180, (-1, 1): 270, (1, -1): 90, (-1, -1): 0 }[(dx, dy)]
    draw.arc([x0, y0, x1, y1], start=start, end=start + 90, fill=color, width=2)
    diamond = [
        (x + dx * 22, y + dy * 8),
        (x + dx * 30, y + dy * 16),
        (x + dx * 22, y + dy * 24),
        (x + dx * 14, y + dy * 16),
    ]
    draw.polygon(diamond, outline=color)
    draw.ellipse(
        [x + dx * 6 - 4, y + dy * 6 - 4, x + dx * 6 + 4, y + dy * 6 + 4],
        fill=color,
    )


def _draw_flourish(draw: ImageDraw.ImageDraw, cx: int, y: int, color, width: int = 260):
    left, right = cx - width // 2, cx + width // 2
    draw.line([(left, y), (cx - 36, y)], fill=color, width=2)
    draw.line([(cx + 36, y), (right, y)], fill=color, width=2)
    draw.arc([cx - 34, y - 16, cx - 6, y + 16], start=200, end=340, fill=color, width=2)
    draw.arc([cx + 6, y - 16, cx + 34, y + 16], start=200, end=340, fill=color, width=2)
    draw.polygon([(cx, y - 10), (cx + 10, y), (cx, y + 10), (cx - 10, y)], outline=color)
    draw.ellipse([cx - 4, y - 4, cx + 4, y + 4], fill=color)


def _draw_crown(draw: ImageDraw.ImageDraw, cx: int, cy: int, color, scale: int = 18):
    """Couronne or, centrée sur (cx, cy)."""
    s = float(scale)
    left, right = cx - s, cx + s
    band_top = cy + s * 0.16
    band_bot = cy + s * 0.58
    body = [
        (left, band_top),
        (cx - s * 0.68, cy - s * 0.08),
        (cx - s * 0.34, band_top),
        (cx, cy - s * 0.62),
        (cx + s * 0.34, band_top),
        (cx + s * 0.68, cy - s * 0.08),
        (right, band_top),
        (right, band_bot),
        (left, band_bot),
    ]
    draw.polygon(body, outline=color)
    draw.line(
        [(left, band_top), (cx - s * 0.68, cy - s * 0.08), (cx - s * 0.34, band_top),
         (cx, cy - s * 0.62), (cx + s * 0.34, band_top),
         (cx + s * 0.68, cy - s * 0.08), (right, band_top)],
        fill=color,
        width=2,
    )
    draw.rectangle([left, band_top, right, band_bot], outline=color, width=2)
    draw.line(
        [(left + 2, band_top + s * 0.18), (right - 2, band_top + s * 0.18)],
        fill=color,
        width=1,
    )
    for jx, jy in (
        (cx, cy - s * 0.62),
        (cx - s * 0.68, cy - s * 0.08),
        (cx + s * 0.68, cy - s * 0.08),
    ):
        draw.ellipse([jx - 3, jy - 3, jx + 3, jy + 3], fill=color)


def _is_dark_image(photo: Image.Image) -> bool:
    sample = photo.resize((24, 24), Image.Resampling.BOX).convert("L")
    return (sum(sample.getdata()) / 576) < 95


def _draw_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, color, letter: str = "GE"):
    r = 48
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    draw.ellipse([cx - r + 7, cy - r + 7, cx + r - 7, cy + r - 7], outline=color, width=1)
    font = _display(20 if len(letter) > 1 else 28)
    tw = _text_width(draw, letter, font)
    bbox = draw.textbbox((0, 0), letter, font=font)
    th = bbox[3] - bbox[1]
    draw.text((cx - tw / 2, cy - th / 2 - 3), letter, font=font, fill=color)


def _paste_medallion(base: Image.Image, cover: Path, cx: int, cy: int, size: int) -> bool:
    try:
        photo = Image.open(cover).convert("RGB")
    except Exception:  # noqa: BLE001
        return False
    side = min(photo.width, photo.height)
    left = (photo.width - side) // 2
    top = (photo.height - side) // 2
    photo = photo.crop((left, top, left + side, top + side)).resize(
        (size, size), Image.Resampling.LANCZOS
    )
    if _is_dark_image(photo):
        return False
    photo = photo.filter(ImageFilter.GaussianBlur(0.35))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, size - 3, size - 3), fill=255)
    ring = Image.new("RGBA", (size + 22, size + 22), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((0, 0, size + 21, size + 21), outline=GOLD + (255,), width=3)
    rd.ellipse((7, 7, size + 14, size + 14), outline=GOLD_DEEP + (230,), width=1)
    px, py = cx - size // 2, cy - size // 2
    base.paste(photo, (px, py), mask)
    base.paste(ring, (px - 11, py - 11), ring)
    return True


def render_invitation_card(invitation: Invitation) -> Image.Image:
    """Carte-lettre cérémonielle 1080×1620, calligraphie et motifs or."""
    event = invitation.event
    cfg = ceremony_settings(event)
    width, height = 1080, 1620
    img = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(img)

    accent = GOLD

    # Filigrane / grain papier
    try:
        grain = Image.effect_noise((width, height), 18).convert("L")
        tint = Image.new("RGB", (width, height), PAPER_INNER)
        img = Image.blend(img, Image.merge("RGB", (grain, grain, grain)), 0.045)
        img = Image.blend(img, tint, 0.18)
        draw = ImageDraw.Draw(img)
    except Exception:  # noqa: BLE001
        pass

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(-height, width, 9):
        od.line([(i, 0), (i + height, height)], fill=(180, 150, 90, 12), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Double cadre
    margin = 38
    draw.rectangle([margin, margin, width - margin, height - margin], outline=accent, width=3)
    draw.rectangle(
        [margin + 14, margin + 14, width - margin - 14, height - margin - 14],
        outline=GOLD_DEEP,
        width=1,
    )
    inner = margin + 14
    _draw_corner(draw, inner, inner, 1, 1, accent)
    _draw_corner(draw, width - inner, inner, -1, 1, accent)
    _draw_corner(draw, inner, height - inner, 1, -1, accent)
    _draw_corner(draw, width - inner, height - inner, -1, -1, accent)

    if invitation.is_vip:
        draw.rectangle([18, 18, width - 18, height - 18], outline=accent, width=1)

    content_w = width - 2 * (inner + 36)

    def line_height(text, font) -> int:
        bbox = draw.textbbox((0, 0), text or "Ay", font=font)
        return max(28, bbox[3] - bbox[1])

    def center_words(text, y, font, fill=INK, gap: int = 14):
        words = [w for w in (text or "").split() if w]
        if not words:
            return 0
        widths = [_text_width(draw, word, font) for word in words]
        total = sum(widths) + gap * (len(words) - 1)
        x = (width - total) / 2
        for word, ww in zip(words, widths):
            draw.text((x, y), word, font=font, fill=fill)
            x += ww + gap
        return line_height(text, font)

    def center_tracked(text, y, font, fill=INK, tracking: int = 3):
        chars = list(text or "")
        if not chars:
            return 0
        widths = [max(4, _text_width(draw, ch, font) if ch != " " else 14) for ch in chars]
        total = sum(widths) + tracking * (len(chars) - 1)
        x = (width - total) / 2
        for ch, cw in zip(chars, widths):
            if ch != " ":
                draw.text((x, y), ch, font=font, fill=fill)
            x += cw + tracking
        return line_height(text, font)

    cover = _cover_path(event)
    y = 86
    used_photo = False
    if cover:
        used_photo = _paste_medallion(img, cover, width // 2, 164, 118)
        draw = ImageDraw.Draw(img)
    if used_photo:
        y = 250
    else:
        _draw_seal(draw, width // 2, 140, accent, "GE")
        y = 220

    kicker = (cfg.get("subtitle") or "Gab Event").upper()
    center_tracked(kicker, y, _display(14), accent, tracking=4)
    y += 48
    _draw_flourish(draw, width // 2, y, accent, 300)
    y += 44

    intro = (cfg.get("welcome") or "").strip() or "Vous êtes cordialement invité(e)"
    intro_font = _script(48)
    y += center_words(intro, y, intro_font, NAVY_2, gap=16) + 24

    name = invitation.full_name or "Invité"
    name_font = _fit_font(draw, name, _script, 82, 44, content_w - 40)
    y += center_words(name, y, name_font, INK, gap=18) + 28
    _draw_flourish(draw, width // 2, y, accent, 200)
    y += 42

    center_words("à l'occasion de", y, _serif(23, italic=True), MUTED, gap=8)
    y += 48
    title = cfg["title"]
    title_font = _fit_font(draw, title, lambda s: _display(s), 32, 20, content_w)
    for line in _wrap_text(draw, title, title_font, content_w):
        y += center_tracked(line, y, title_font, INK, tracking=2) + 18

    y += 28
    meta_font = _serif(28, semibold=True)
    when = "  ·  ".join(part for part in (cfg["date"], cfg["time"]) if part)
    center_words(when, y, meta_font, NAVY, gap=8)
    y += 50
    for line in _wrap_text(draw, str(cfg["venue"]), _serif(26), content_w):
        center_words(line, y, _serif(26), NAVY, gap=8)
        y += 46

    places = invitation.places or 1
    place_txt = (
        "Invitation nominative  ·  1 personne"
        if places == 1
        else f"Invitation nominative  ·  {places} personnes"
    )
    y += 16
    center_words(place_txt, y, _serif(20, italic=True), MUTED, gap=8)
    y += 56

    qr = build_qr_image(invitation.code, box_size=10, border=2)
    qr_size = 220
    qr = qr.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    qx = (width - qr_size) // 2
    qy = y + 24
    if qy + qr_size + 200 > height - 56:
        qy = height - qr_size - 210
    frame = 20
    draw.rounded_rectangle(
        [qx - frame, qy - frame, qx + qr_size + frame, qy + qr_size + frame],
        radius=10,
        outline=accent,
        width=2,
    )
    draw.rounded_rectangle(
        [qx - 10, qy - 10, qx + qr_size + 10, qy + qr_size + 10],
        radius=6,
        fill=WHITE,
        outline=GOLD_DEEP,
        width=1,
    )
    img.paste(qr, (qx, qy))
    draw = ImageDraw.Draw(img)
    center_tracked(invitation.code, qy + qr_size + 32, _display(17), INK, tracking=3)

    footer = (cfg.get("footer") or "").strip() or "Veuillez présenter cette invitation à l'entrée."
    footer_font = _serif(18, italic=True)
    fy = qy + qr_size + 80
    for line in _wrap_text(draw, footer, footer_font, content_w):
        center_words(line, fy, footer_font, MUTED, gap=7)
        fy += 28
        if fy > height - 180:
            break
    badge = "VIP" if invitation.is_vip else "INVITÉ"
    badge_font = _display(28)
    badge_y = min(fy + 20, height - 132)
    if invitation.is_vip:
        chars = list(badge)
        tracking = 5
        widths = [max(4, _text_width(draw, ch, badge_font)) for ch in chars]
        tracked = sum(widths) + tracking * (len(chars) - 1)
        crown_w = 52
        gap = 16
        start = (width - (crown_w + gap + tracked)) / 2
        _draw_crown(draw, start + crown_w / 2, badge_y + 16, accent, scale=24)
        x = start + crown_w + gap
        for ch, cw in zip(chars, widths):
            draw.text((x, badge_y), ch, font=badge_font, fill=accent)
            x += cw + tracking
    else:
        center_tracked(badge, badge_y, badge_font, accent, tracking=5)
    _draw_flourish(draw, width // 2, height - 70, accent, 220)
    center_tracked("GAB EVENT", height - 58, _display(12), accent, tracking=6)

    return img


def generate_invitation_card(
    invitation: Invitation, save: bool = True
) -> tuple[bytes, Path | None]:
    card = render_invitation_card(invitation)
    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()

    path = None
    if save:
        folder = "vip" if invitation.is_vip else "standard"
        # Compat ancien dossier
        legacy = invitations_dir() / "recipiendaires"
        out = invitations_dir() / folder
        out.mkdir(parents=True, exist_ok=True)
        if legacy.exists() and folder == "standard":
            pass
        path = out / invitation_filename(invitation)
        path.write_bytes(data)
        invitation.invitation_generated = True
        invitation.invitation_generated_at = timezone.now()
        invitation.save(
            update_fields=["invitation_generated", "invitation_generated_at"]
        )
    return data, path


def build_invitations_zip(
    invitations=None,
    only_missing: bool = False,
) -> tuple[bytes, dict]:
    """Generate cards and return ZIP bytes + summary."""
    qs = invitations if invitations is not None else Invitation.objects.all()
    if hasattr(qs, "order_by"):
        qs = qs.order_by("participant_type", "last_name", "first_name")

    summary = {
        "recipient_total": 0,
        "vip_total": 0,
        "generated": 0,
        "skipped": 0,
        "errors": 0,
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for inv in qs:
            if inv.is_vip:
                summary["vip_total"] += 1
                folder = "invitations/vip"
                disk_folder = "vip"
            else:
                summary["recipient_total"] += 1
                folder = "invitations/standard"
                disk_folder = "standard"

            if only_missing and inv.invitation_generated:
                existing = invitations_dir() / disk_folder / invitation_filename(inv)
                if not existing.exists():
                    existing = (
                        invitations_dir()
                        / "recipiendaires"
                        / invitation_filename(inv)
                    )
                if existing.exists():
                    zf.write(existing, f"{folder}/{existing.name}")
                    summary["skipped"] += 1
                    continue
            try:
                data, _ = generate_invitation_card(inv, save=True)
                zf.writestr(f"{folder}/{invitation_filename(inv)}", data)
                summary["generated"] += 1
            except Exception:  # noqa: BLE001
                summary["errors"] += 1
    return buf.getvalue(), summary
