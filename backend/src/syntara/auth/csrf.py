"""CSRF protection for cookie-authenticated endpoints.

Implements the Synchronizer Token pattern with HMAC derivation:

1. On login/OIDC callback the server generates a random **seed** and
   stores it in an ``HttpOnly`` cookie (``ao_csrf_token``).
2. The server derives a **form token** via
   ``HMAC-SHA256(server_secret, seed)`` and delivers it to the SPA in
   the response body (or redirect query parameter).
3. The SPA stores the form token in memory and sends it in the
   ``X-CSRF-Token`` header on subsequent requests.
4. On protected endpoints the server reads the seed from the cookie,
   recomputes the HMAC, and compares it to the header value using
   ``hmac.compare_digest`` (timing-safe).

The HMAC derivation means that even if an attacker can somehow read
the cookie (e.g. via a subdomain XSS), they cannot forge the form
token without the server-side secret.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING

from syntara.auth.cookies import CSRF_COOKIE_NAME
from syntara.auth.exceptions import CSRFErrorCode, CSRFValidationError
from syntara.core.config.base import get_encryption_key

if TYPE_CHECKING:
    from fastapi import Request

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "ERR_COOKIE_MISSING",
    "ERR_HEADER_MISSING",
    "ERR_TOKEN_MISMATCH",
    "CSRFValidationError",
    "derive_csrf_form_token",
    "generate_csrf_seed",
    "validate_csrf",
]

CSRF_HEADER_NAME = "X-CSRF-Token"

ERR_COOKIE_MISSING = "CSRF cookie missing"
ERR_HEADER_MISSING = "CSRF token header missing"
ERR_TOKEN_MISMATCH = "CSRF token mismatch"  # noqa: S105


def generate_csrf_seed() -> str:
    """Generate a cryptographically random seed for the CSRF cookie.

    Returns:
        A URL-safe random string (32 bytes of entropy).

    """
    return secrets.token_urlsafe(32)


def derive_csrf_form_token(seed: str) -> str:
    """Derive the CSRF form token from *seed* using HMAC-SHA256.

    The server-side ``secret_encryption_key`` is used as the HMAC key
    so that knowledge of the cookie seed alone is insufficient to
    forge the form token.

    Args:
        seed: The random seed stored in the CSRF cookie.

    Returns:
        Hex-encoded HMAC-SHA256 digest.

    """
    key = get_encryption_key().get_secret_value().encode()
    return hmac.new(key, seed.encode(), hashlib.sha256).hexdigest()


def validate_csrf(request: Request) -> None:
    """Validate the CSRF form token against the cookie seed.

    Reads the seed from the ``ao_csrf_token`` cookie, recomputes the
    expected form token, and compares it to the value in the
    ``X-CSRF-Token`` request header using a timing-safe comparison.

    Args:
        request: The incoming FastAPI/Starlette request.

    Raises:
        CSRFValidationError: If the cookie is missing, the header is
            missing, or the values do not match.

    """
    seed = request.cookies.get(CSRF_COOKIE_NAME)
    if not seed:
        raise CSRFValidationError(ERR_COOKIE_MISSING, error_code=CSRFErrorCode.COOKIE_MISSING)

    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not header_token:
        raise CSRFValidationError(ERR_HEADER_MISSING, error_code=CSRFErrorCode.HEADER_MISSING)

    expected = derive_csrf_form_token(seed)
    if not hmac.compare_digest(expected, header_token):
        raise CSRFValidationError(ERR_TOKEN_MISMATCH, error_code=CSRFErrorCode.TOKEN_MISMATCH)
