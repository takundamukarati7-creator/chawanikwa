"""Small pure helpers: name/phone normalisation and privacy masking."""
import re

from django.core.exceptions import ValidationError

LAST5_RE = re.compile(r"^[A-Z0-9]{5}$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+)*$", re.UNICODE)


def normalize_name(name: str) -> str:
    """Lower-case, collapse whitespace. Used for searching and matching."""
    return " ".join((name or "").split()).casefold()


def clean_display_name(name: str) -> str:
    return " ".join((name or "").split())


def name_tokens(name_key: str) -> set:
    return {t for t in re.split(r"[ '\-.]+", name_key) if t}


def names_compatible(key_a: str, key_b: str) -> bool:
    """Two names are compatible if they share at least two name parts (or all parts of the shorter name)."""
    a, b = name_tokens(key_a), name_tokens(key_b)
    if not a or not b:
        return False
    return len(a & b) >= min(2, len(a), len(b))


def mask_name(full_name: str) -> str:
    """'Tinashe Moyo' -> 'Tin***e M.'  Only the shape of the name is shown publicly."""
    parts = clean_display_name(full_name).split(" ")
    if not parts or not parts[0]:
        return ""
    first = parts[0]
    n = len(first)
    if n <= 1:
        masked_first = first
    elif n <= 4:
        masked_first = first[0] + "*" * (n - 1)
    else:
        masked_first = first[:3] + "*" * (n - 4) + first[-1]
    initials = " ".join(p[0].upper() + "." for p in parts[1:] if p)
    return f"{masked_first} {initials}".strip()


def normalize_phone(raw: str) -> str:
    """Return an E.164 number. Zimbabwean local numbers (07x...) become +263..."""
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"0\d{9}", s):
        s = "+263" + s[1:]
    elif re.fullmatch(r"263\d{9}", s):
        s = "+" + s
    if not re.fullmatch(r"\+\d{8,15}", s):
        raise ValidationError("Enter a valid phone number, for example 0771234567 or +263771234567.")
    return s


def whatsapp_link(phone_e164: str, text: str) -> str:
    from urllib.parse import quote

    return f"https://wa.me/{phone_e164.lstrip('+')}?text={quote(text)}"


def whatsapp_web_link(phone_e164: str, text: str) -> str:
    """Opens the chat straight in WhatsApp Web, which works even when the desktop app ignores wa.me links."""
    from urllib.parse import quote

    return f"https://web.whatsapp.com/send?phone={phone_e164.lstrip('+')}&text={quote(text)}"
