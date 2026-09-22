"""
Génération des QR codes PNG.

Le contenu du QR est **uniquement** le code invitation (ex. ATC24-XXXXXX),
sans URL — pour rester robuste hors-ligne côté décodage terrain.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import qrcode
from django.conf import settings
from qrcode.constants import ERROR_CORRECT_M

from .models import Invitation


def qr_output_dir() -> Path:
    path = Path(settings.BASE_DIR) / "generated_qr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_qr_image(code: str, box_size: int = 12, border: int = 2):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(code)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


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
