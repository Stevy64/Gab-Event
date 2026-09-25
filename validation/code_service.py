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
VIP_EXTRACT_RE = re.compile(
    rf"VIP[-_]?([{CODE_ALPHABET}]{{{CODE_SUFFIX_LENGTH}}})",
    re.IGNORECASE,
)
SUFFIX_RE = re.compile(
    rf"[-_]([{CODE_ALPHABET}]{{{CODE_SUFFIX_LENGTH}}})",
    re.IGNORECASE,
)


def normalize_code(raw: str | None) -> str:
    """
    Normalise un code scanné ou saisi.

    - Supprime les espaces, majuscules
    - VIP-XXXXXX prioritaire (même entouré de texte)
    - Puis PREFIX-XXXXXX (ATC24, préfixe événement, etc.)
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    compact = CODE_NORMALIZE_RE.sub("", text).upper()

    vip = VIP_EXTRACT_RE.search(compact)
    if vip:
        return f"{VIP_CODE_PREFIX}-{vip.group(1).upper()}"

    candidates: list[tuple[str, str]] = []
    recipient = RECIPIENT_CODE_PREFIX.upper()
    known_prefixes = {recipient, "ATC24", "GAE24", "GAE25", "GAE26"}
    for hm in SUFFIX_RE.finditer(compact):
        suffix = hm.group(1).upper()
        before = compact[: hm.start()]
        m = re.search(r"([A-Z][A-Z0-9]{1,23})$", before)
        if not m:
            continue
        full_pref = m.group(1)
        candidates.append((full_pref, suffix))
        # Compat bruit avant préfixe connu (ex. XXATC24-…, url/ATC24-…)
        for known in known_prefixes:
            if full_pref.endswith(known) and full_pref != known:
                candidates.append((known, suffix))

    if not candidates:
        return compact

    for pref, suf in candidates:
        if pref in known_prefixes:
            return f"{pref}-{suf}"

    # Préfixe maximal juste avant le séparateur (premier candidat de la dernière occurrence)
    pref, suf = candidates[-1]
    # Si plusieurs pour le même suffixe, prendre le plus long (préfixe complet)
    same_suf = [c for c in candidates if c[1] == suf]
    pref = max(same_suf, key=lambda c: len(c[0]))[0]
    return f"{pref}-{suf}"


def prefix_for_type(participant_type: str, event=None) -> str:
    """
    Préfixe QR :
    - VIP : VIP
    - Standard avec Event : event.code_prefix
    - Fallback settings : ATC24
    """
    if participant_type == PARTICIPANT_VIP:
        return VIP_CODE_PREFIX
    if event is not None and getattr(event, "code_prefix", None):
        return event.code_prefix.upper()
    return RECIPIENT_CODE_PREFIX


def generate_invitation_code(
    participant_type: str = PARTICIPANT_RECIPIENT,
    event=None,
) -> str:
    """Génère un code unique PREFIX-XXXXXX (secrets)."""
    prefix = prefix_for_type(participant_type, event=event)
    for _ in range(64):
        suffix = "".join(
            secrets.choice(CODE_ALPHABET) for _ in range(CODE_SUFFIX_LENGTH)
        )
        code = f"{prefix}-{suffix}"
        if not Invitation.objects.filter(code__iexact=code).exists():
            return code
    raise RuntimeError("Impossible de générer un code unique.")


def ensure_unique_code(
    participant_type: str,
    preferred: str | None = None,
    event=None,
) -> str:
    code = normalize_code(preferred)
    if code and not Invitation.objects.filter(code__iexact=code).exists():
        return code
    return generate_invitation_code(participant_type, event=event)


def create_invitation_with_unique_code(**kwargs) -> Invitation:
    participant_type = kwargs.get("participant_type", PARTICIPANT_RECIPIENT)
    event = kwargs.get("event")
    if not kwargs.get("code"):
        kwargs["code"] = generate_invitation_code(participant_type, event=event)
    for _ in range(8):
        try:
            return Invitation.objects.create(**kwargs)
        except IntegrityError:
            kwargs["code"] = generate_invitation_code(participant_type, event=event)
    raise RuntimeError("Échec de création d'invitation unique.")
