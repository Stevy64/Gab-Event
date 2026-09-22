"""Secure unique invitation code generation and scan-text normalization."""
from __future__ import annotations

import re
import secrets

from django.db import IntegrityError

from .constants import (
    CODE_ALPHABET,
    CODE_SUFFIX_LENGTH,
    PARTICIPANT_RECIPIENT,
    PARTICIPANT_VIP,
    RECIPIENT_CODE_PREFIX,
    VIP_CODE_PREFIX,
)
from .models import Invitation

CODE_NORMALIZE_RE = re.compile(r"\s+")
# Extrait ATC24-/VIP- même si le QR / collage contient du bruit (URL, préfixe, etc.)
CODE_EXTRACT_RE = re.compile(
    rf"({re.escape(RECIPIENT_CODE_PREFIX)}|{re.escape(VIP_CODE_PREFIX)})[-_]?([{CODE_ALPHABET}]{{{CODE_SUFFIX_LENGTH}}})",
    re.IGNORECASE,
)


def normalize_code(raw: str | None) -> str:
    """
    Normalise un code scanné ou saisi.

    - Supprime les espaces
    - Met en majuscules
    - Si un motif ATC24-XXXXXX / VIP-XXXXXX est présent dans le texte, le renvoie
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    compact = CODE_NORMALIZE_RE.sub("", text).upper()
    match = CODE_EXTRACT_RE.search(compact)
    if match:
        return f"{match.group(1).upper()}-{match.group(2).upper()}"
    return compact


def prefix_for_type(participant_type: str) -> str:
    if participant_type == PARTICIPANT_VIP:
        return VIP_CODE_PREFIX
    return RECIPIENT_CODE_PREFIX


def generate_invitation_code(participant_type: str = PARTICIPANT_RECIPIENT) -> str:
    """Generate ATC24-XXXXXX or VIP-XXXXXX using secrets. Unique in DB."""
    prefix = prefix_for_type(participant_type)
    for _ in range(64):
        suffix = "".join(
            secrets.choice(CODE_ALPHABET) for _ in range(CODE_SUFFIX_LENGTH)
        )
        code = f"{prefix}-{suffix}"
        if not Invitation.objects.filter(code__iexact=code).exists():
            return code
    raise RuntimeError("Impossible de générer un code unique.")


def ensure_unique_code(participant_type: str, preferred: str | None = None) -> str:
    code = normalize_code(preferred)
    if code and not Invitation.objects.filter(code__iexact=code).exists():
        return code
    return generate_invitation_code(participant_type)


def create_invitation_with_unique_code(**kwargs) -> Invitation:
    participant_type = kwargs.get("participant_type", PARTICIPANT_RECIPIENT)
    if not kwargs.get("code"):
        kwargs["code"] = generate_invitation_code(participant_type)
    for _ in range(8):
        try:
            return Invitation.objects.create(**kwargs)
        except IntegrityError:
            kwargs["code"] = generate_invitation_code(participant_type)
    raise RuntimeError("Échec de création d'invitation unique.")
