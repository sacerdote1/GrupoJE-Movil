"""Utilidades de autenticación sin dependencias externas."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os


ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Devuelve (válida, requiere_actualización). Acepta legado solo para migrarlo."""
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(str(stored or ""), password), True
    try:
        _, iterations, salt, expected = stored.split("$", 3)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(expected)), False
    except (ValueError, TypeError):
        return False, False
