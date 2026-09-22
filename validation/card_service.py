"""
Cartes d'invitation PNG (identité + QR) et archive ZIP pour distribution.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .constants import ceremony_settings
from .models import Invitation
from .qr_service import build_qr_image

NAVY = (15, 26, 42)
NAVY_2 = (13, 27, 42)
ORANGE = (242, 101, 34)
WHITE = (255, 255, 255)
GOLD = (212, 175, 55)
MUTED = (180, 190, 205)


def _font(size: int, bold: bool = False):
    candidates = [
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


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", (value or "").strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "invite"


def invitation_filename(invitation: Invitation) -> str:
    prefix = "VIP" if invitation.is_vip else "ATC24"
    return (
        f"invitation_{prefix}_"
        f"{safe_filename_part(invitation.first_name)}_"
        f"{safe_filename_part(invitation.last_name)}.png"
    )


def invitations_dir() -> Path:
    path = Path(settings.BASE_DIR) / "generated_invitations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_invitation_card(invitation: Invitation) -> Image.Image:
    """Render a printable invitation card (1080×1620)."""
    cfg = ceremony_settings()
    width, height = 1080, 1620
    img = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(img)

    # Header band
    draw.rectangle([0, 0, width, 220], fill=NAVY)
    accent = GOLD if invitation.is_vip else ORANGE
    draw.rectangle([0, 220, width, 232], fill=accent)

    title_font = _font(36, bold=True)
    sub_font = _font(28, bold=True)
    body_font = _font(28)
    name_font = _font(48, bold=True)
    small_font = _font(24)
    code_font = _font(30, bold=True)

    def center(text, y, font, fill=WHITE):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) / 2, y), text, font=font, fill=fill)

    center(cfg["title"].upper(), 58, title_font, WHITE)
    center(cfg["subtitle"].upper(), 118, sub_font, accent)

    badge = "INVITATION VIP" if invitation.is_vip else "INVITATION"
    badge_font = _font(26, bold=True)
    bw = draw.textbbox((0, 0), badge, font=badge_font)[2]
    bx = (width - bw) / 2 - 28
    draw.rounded_rectangle([bx, 280, bx + bw + 56, 340], radius=24, fill=accent)
    center(badge, 292, badge_font, WHITE if not invitation.is_vip else NAVY)

    intro = (
        "Nous avons l'honneur de convier"
        if invitation.is_vip
        else "Nous avons le plaisir de convier"
    )
    center(intro, 390, body_font, NAVY_2)
    center(invitation.full_name, 450, name_font, NAVY)
    cat = invitation.category or (
        "Récipiendaire" if not invitation.is_vip else "VIP"
    )
    center(cat.upper(), 520, sub_font, accent)

    center("à la cérémonie de remise des diplômes.", 590, body_font, NAVY_2)

    meta_y = 680
    for label, value in (
        ("📅  Date", cfg["date"]),
        ("🕐  Heure", cfg["time"]),
        ("📍  Lieu", cfg["venue"]),
    ):
        center(f"{label}  ·  {value}", meta_y, small_font, NAVY_2)
        meta_y += 48

    center("Invitation nominative · 1 personne", meta_y + 20, sub_font, ORANGE)

    # QR
    qr = build_qr_image(invitation.code, box_size=10, border=2)
    qr_size = 360
    qr = qr.resize((qr_size, qr_size))
    qx = (width - qr_size) // 2
    qy = 960
    draw.rectangle([qx - 16, qy - 16, qx + qr_size + 16, qy + qr_size + 16], outline=NAVY, width=3)
    img.paste(qr, (qx, qy))

    center(invitation.code, qy + qr_size + 36, code_font, NAVY)
    center(cfg["footer"], height - 90, small_font, MUTED)

    # Side accent for VIP
    if invitation.is_vip:
        draw.rectangle([0, 232, 14, height], fill=GOLD)
        draw.rectangle([width - 14, 232, width, height], fill=GOLD)

    return img


def generate_invitation_card(invitation: Invitation, save: bool = True) -> tuple[bytes, Path | None]:
    card = render_invitation_card(invitation)
    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()

    path = None
    if save:
        folder = "vip" if invitation.is_vip else "recipiendaires"
        out = invitations_dir() / folder
        out.mkdir(parents=True, exist_ok=True)
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
            else:
                summary["recipient_total"] += 1
                folder = "invitations/recipiendaires"

            if only_missing and inv.invitation_generated:
                existing = invitations_dir() / (
                    "vip" if inv.is_vip else "recipiendaires"
                ) / invitation_filename(inv)
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
