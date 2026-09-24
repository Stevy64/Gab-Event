"""
Identité visuelle Gab Event : défauts (bleu nuit, visuels marque)
et catalogue d'images du carrousel / événements non customisés.
"""
from __future__ import annotations

from datetime import date

from django.contrib.staticfiles.storage import staticfiles_storage

# Bleu nuit — couleur par défaut tant que l'organisateur n'a pas customisé
DEFAULT_PRIMARY_COLOR = "#1A2744"
LEGACY_PRIMARY_COLOR = "#F26522"

DEFAULT_COVER = "img/ceremony-bg.jpg"
DEFAULT_LOGO = "icons/icon-192.png"

GALLERY: tuple[dict[str, str], ...] = (
    {
        "file": "img/ceremony-bg.jpg",
        "label": "Gab Event",
        "caption": "Votre plateforme d'invitations",
    },
    {
        "file": "img/gallery-soiree.jpg",
        "label": "Soirée",
        "caption": "Une table prête pour vos invités",
    },
    {
        "file": "img/gallery-salle.jpg",
        "label": "Réception",
        "caption": "La salle, avant l'arrivée des convives",
    },
    {
        "file": "img/gallery-centre-table.jpg",
        "label": "Gala",
        "caption": "Le détail qui donne le ton",
    },
    {
        "file": "img/gallery-banquet.jpg",
        "label": "Banquet",
        "caption": "Un service soigné, de bout en bout",
    },
)


def year_code_prefix(when: date | None = None) -> str:
    """Préfixe invitations : GAE + 2 chiffres de l'année (ex. GAE26)."""
    return f"GAE{(when or date.today()).strftime('%y')}"


def static_url(path: str) -> str:
    return staticfiles_storage.url(path)


def auth_cover_url() -> str:
    """Fond des pages auth : image galerie en position 0 (Gab Event)."""
    try:
        from .models import GalleryImage

        first = (
            GalleryImage.objects.filter(is_active=True)
            .order_by("display_order", "id")
            .first()
        )
        if first and first.url:
            return first.url
        gab = (
            GalleryImage.objects.filter(label__iexact="Gab Event")
            .order_by("display_order", "id")
            .first()
        )
        if gab and gab.url:
            return gab.url
    except Exception:
        pass
    return static_url(DEFAULT_COVER)


def category_cover_url(event_type: str) -> str:
    """Visuel par défaut du type d’événement, sinon couverture site."""
    slug = (event_type or "").strip()
    if slug:
        try:
            from .models import EventCategory

            cat = EventCategory.objects.filter(slug=slug).first()
            if cat:
                url = cat.image_url
                if url:
                    return url
        except Exception:
            pass
    return default_cover_url()


def default_cover_url() -> str:
    try:
        from .models import SiteSettings

        site = SiteSettings.objects.first()
        if site and site.default_cover:
            return site.default_cover.url
    except Exception:
        pass
    return static_url(DEFAULT_COVER)


def site_brand() -> dict[str, str]:
    """Logo public + version de cache (réglages console)."""
    version = "0"
    try:
        from .models import SiteSettings

        site = SiteSettings.objects.first()
        if site:
            if site.updated_at:
                version = str(int(site.updated_at.timestamp()))
            if site.logo:
                try:
                    return {"logo_url": site.logo.url, "version": version}
                except ValueError:
                    pass
    except Exception:
        pass
    return {"logo_url": static_url(DEFAULT_LOGO), "version": version}


def default_logo_url() -> str:
    return site_brand()["logo_url"]


def render_default_mark(size: int):
    """Pictogramme officiel (coins or + losange) — fallback si aucun logo uploadé."""
    from PIL import Image, ImageDraw

    size = max(16, int(size))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    navy = (11, 18, 32, 255)
    gold = (232, 214, 168, 255)
    diamond = (201, 162, 74, 255)
    scale = size / 512
    radius = max(4, int(112 * scale))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=navy)

    def sc(value: float) -> float:
        return value * scale

    bar_r = max(1, int(6 * scale))
    bars = (
        (96, 96, 120, 28),
        (96, 96, 28, 120),
        (296, 96, 120, 28),
        (388, 96, 28, 120),
        (96, 388, 120, 28),
        (96, 296, 28, 120),
    )
    for x, y, w, h in bars:
        draw.rounded_rectangle(
            (sc(x), sc(y), sc(x + w), sc(y + h)),
            radius=bar_r,
            fill=gold,
        )
    draw.polygon(
        [(sc(256), sc(180)), (sc(320), sc(256)), (sc(256), sc(332)), (sc(192), sc(256))],
        fill=diamond,
    )
    return img


def write_default_static_icons(base_dir=None) -> list[str]:
    """Génère les PNG manquants dans static/icons/."""
    from pathlib import Path

    from django.conf import settings
    from PIL import Image

    root = Path(base_dir or settings.BASE_DIR) / "static" / "icons"
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    specs = (
        ("icon-192.png", 192, 0.0),
        ("icon-512.png", 512, 0.0),
        ("apple-touch-icon.png", 180, 0.0),
        ("icon-192-maskable.png", 192, 0.12),
        ("icon-512-maskable.png", 512, 0.12),
    )
    for name, size, pad in specs:
        if pad:
            inner = max(16, int(size * (1 - 2 * pad)))
            mark = render_default_mark(inner)
            canvas = Image.new("RGBA", (size, size), (11, 18, 32, 255))
            offset = (size - inner) // 2
            canvas.paste(mark, (offset, offset), mark)
            canvas.save(root / name, "PNG")
        else:
            render_default_mark(size).save(root / name, "PNG")
        written.append(str(root / name))
    return written


def display_color(value: str | None) -> str:
    raw = (value or "").strip().upper()
    if not raw:
        return DEFAULT_PRIMARY_COLOR
    return raw


def gallery_slides() -> list[dict[str, str]]:
    try:
        from .models import GalleryImage

        rows = list(
            GalleryImage.objects.filter(is_active=True).order_by("display_order", "id")
        )
        slides = []
        for row in rows:
            url = row.url
            if not url:
                continue
            slides.append(
                {"url": url, "label": row.label, "caption": row.caption or ""}
            )
        if slides:
            return slides
    except Exception:
        pass
    slides = []
    for item in GALLERY:
        slides.append(
            {
                "url": static_url(item["file"]),
                "label": item["label"],
                "caption": item["caption"],
            }
        )
    return slides
