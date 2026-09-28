"""
Génération des QR codes PNG.

Le contenu du QR est **uniquement** le code (invitation ATC24-XXXXXX ou
billet GEB-XXXX-XXXX), sans URL — robuste hors-ligne au scan.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import qrcode
from django.conf import settings
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

from .models import Invitation


def qr_output_dir() -> Path:
    path = Path(settings.BASE_DIR) / "generated_qr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_qr_image(
    code: str,
    box_size: int = 12,
    border: int = 2,
    *,
    high_contrast: bool = False,
):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H if high_contrast else ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(code)
    qr.make(fit=True)
    ink = "#000000" if high_contrast else "#1A2744"
    return qr.make_image(fill_color=ink, back_color="white").convert("RGB")


def generate_invitation_qr(invitation: Invitation, outdir: Path | None = None) -> Path:
    """Write PNG QR for an invitation; returns file path."""
    outdir = outdir or qr_output_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{invitation.code}.png"
    img = build_qr_image(invitation.code)
    img.save(path, format="PNG")
    return path


def qr_png_bytes(code: str) -> bytes:
    buf = BytesIO()
    build_qr_image(code).save(buf, format="PNG")
    return buf.getvalue()
