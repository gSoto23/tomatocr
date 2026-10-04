"""Checks against bots on the public contact form (POST /contacto).

Two kinds:
- What a person typed wrong (phone, a name with numbers): clean_lead in app/utils/leads.py
  shows the error so they can fix it.
- Signs of a bot (spam_reasons here): the bot gets the usual "thank you"; the request is kept
  as an already discarded account (Clientes → Descartados, "Spam automático: …"), without
  e-mail, so nothing reaches the sellers and nothing tells the bot what gave it away.
"""
import hashlib
import hmac
import re
import time
from typing import Dict, List, Optional

from app.core.config import settings

# --- Phone ------------------------------------------------------------------------------
# Costa Rica: 8 digits starting with 2 (landline), 4, 5, 6, 7 or 8; optional +506 / 506.
# Abroad: must start with + and have 8 to 15 digits (E.164).
CR_NUMBER = re.compile(r"^[245678]\d{7}$")
PHONE_CHARS = re.compile(r"^\+?[\d\s\-().]+$")


def phone_problem(phone: str) -> Optional[str]:
    """Why the phone is not valid, or None."""
    if not phone:
        return None
    text = phone.strip()
    if not PHONE_CHARS.match(text):
        return "Revisá el teléfono: solo números (ej. 8888 8888)"
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        if digits.startswith("506"):
            return None if CR_NUMBER.match(digits[3:]) else "Revisá el teléfono: en Costa Rica son 8 dígitos después de +506"
        return None if 8 <= len(digits) <= 15 else "Revisá el teléfono: con código de país, de 8 a 15 dígitos"
    if len(digits) == 11 and digits.startswith("506"):
        digits = digits[3:]
    if CR_NUMBER.match(digits):
        return None
    return "Revisá el teléfono: 8 dígitos (ej. 8888 8888), o con + y el código si es de otro país"


def name_problem(name: str) -> Optional[str]:
    if name and not re.search(r"[^\W\d_]", name):
        return "Escribí tu nombre"
    if re.search(r"\d", name or ""):
        return "Escribí tu nombre sin números"
    return None


# --- Form token: when the page was shown ---------------------------------------------------
# A hidden field with the time the form was rendered, signed with SECRET_KEY. A person takes
# more than a few seconds to fill it in; a bot posts at once, or without loading the page.
MIN_SECONDS = 3


def _sign(stamp: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"contacto:{stamp}".encode(), hashlib.sha256).hexdigest()[:20]


def form_token(now: Optional[float] = None) -> str:
    stamp = str(int(now if now is not None else time.time()))
    return f"{stamp}.{_sign(stamp)}"


def token_problem(token: str, now: Optional[float] = None) -> Optional[str]:
    try:
        stamp, signature = (token or "").split(".", 1)
        int(stamp)
    except ValueError:
        return "sin la marca del formulario"
    if not hmac.compare_digest(signature, _sign(stamp)):
        return "marca del formulario alterada"
    elapsed = (now if now is not None else time.time()) - int(stamp)
    if elapsed < MIN_SECONDS:
        return f"enviado en {max(0, int(elapsed))} s"
    return None


# --- Content ---------------------------------------------------------------------------------
# A word that mixes letters and digits, 10+ characters long, with at least 3 of each:
# "NAYUYUTY410456NEYRTHYT". Codes people write (licitación 2025LD-000082) are shorter or
# split by hyphens.
GIBBERISH = re.compile(r"\b(?=\w*\d\w*\d\w*\d)(?=(?:\w*[^\W\d_]){3})\w{10,}\b")

# Throwaway e-mail services seen in spam (add more as they appear).
DISPOSABLE_DOMAINS = {
    "belettersmail.com", "mailinator.com", "guerrillamail.com", "guerrillamail.info", "sharklasers.com",
    "10minutemail.com", "temp-mail.org", "tempmail.com", "tempmail.net", "yopmail.com", "trashmail.com",
    "getnada.com", "dispostable.com", "maildrop.cc", "mohmal.com", "throwawaymail.com", "fakeinbox.com",
    "emailondeck.com", "mintemail.com", "spamgourmet.com", "mailnesia.com", "tempr.email", "discard.email",
}


def spam_reasons(lead: Dict, token: str, now: Optional[float] = None) -> List[str]:
    """Signs that a bot sent it. Empty for a person."""
    reasons = []
    problem = token_problem(token, now)
    if problem:
        reasons.append(problem)
    for field, label in (("name", "nombre"), ("company", "empresa"), ("message", "mensaje")):
        if GIBBERISH.search(lead.get(field) or ""):
            reasons.append(f"texto sin sentido en {label}")
    domain = (lead.get("email") or "").rpartition("@")[2]
    if domain in DISPOSABLE_DOMAINS:
        reasons.append(f"correo desechable ({domain})")
    return reasons
