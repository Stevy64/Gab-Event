"""Upload et validation sécurisée des flyers événement."""
from __future__ import annotations

import io
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_FLYER_BYTES = 5 * 1024 * 1024
MAX_DIMENSION = 2000


def validate_flyer_upload(uploaded) -> None:
    name = (getattr(uploaded, "name", "") or "").lower()
    ext = Path(name).suffix
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Format non autorisé. Utilisez JPG, JPEG, PNG ou WEBP."
        )
    size = getattr(uploaded, "size", 0) or 0
    if size > MAX_FLYER_BYTES:
        raise ValidationError("Fichier trop volumineux (max 5 Mo).")

    content_type = getattr(uploaded, "content_type", "") or ""
    # Ne pas faire confiance uniquement au content_type navigateur
    uploaded.seek(0)
    header = uploaded.read(32)
    uploaded.seek(0)
    if not _looks_like_image(header, ext):
        raise ValidationError("Le fichier n'est pas une image valide.")
    if content_type and content_type not in ALLOWED_MIME:
        # Accepter si le contenu est une vraie image malgré MIME douteux
        pass

    try:
        img = Image.open(uploaded)
        img.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Image illisible : {exc}") from exc
    finally:
        uploaded.seek(0)


def _looks_like_image(header: bytes, ext: str) -> bool:
    if header.startswith(b"\xff\xd8\xff"):
        return True
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True
    return False


def process_flyer_image(uploaded) -> ContentFile:
    """Redimensionne / recompresse raisonnablement le flyer."""
    validate_flyer_upload(uploaded)
    uploaded.seek(0)
    img = Image.open(uploaded)
    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    name = Path(getattr(uploaded, "name", "flyer.jpg")).stem + ".jpg"
    return ContentFile(buf.getvalue(), name=name)
