"""Cookie helpers for authentication.

Provides functions to set, read, and clear the HttpOnly cookies used by
the auth system: the refresh-token cookie and the CSRF seed cookie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from fastapi import Request, Response

# Hardcoded cookie settings (not user-configurable for security)
COOKIE_NAME = "ao_refresh_token"
COOKIE_PATH = "/api/v1/auth"
COOKIE_SAMESITE: Literal["lax"] = "lax"

CSRF_COOKIE_NAME = "ao_csrf_token"
CSRF_COOKIE_PATH = "/api/v1/auth"
CSRF_COOKIE_SAMESITE: Literal["lax"] = "lax"


def set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    """Set the refresh-token cookie on *response*.

    Args:
        response: The outgoing FastAPI/Starlette response.
        token: The encoded JWT refresh token.
        max_age: Cookie lifetime in seconds.

    """
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=COOKIE_SAMESITE,
        domain=settings.cookie_domain,
        path=COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Expire / delete the refresh-token cookie on *response*.

    Args:
        response: The outgoing FastAPI/Starlette response.

    """
    settings = get_settings()
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=COOKIE_SAMESITE,
        domain=settings.cookie_domain,
        path=COOKIE_PATH,
    )


def get_refresh_token_from_cookie(request: Request) -> str | None:
    """Read the refresh token from the incoming request cookie.

    Args:
        request: The incoming FastAPI/Starlette request.

    Returns:
        The raw JWT string, or ``None`` if the cookie is absent.

    """
    return request.cookies.get(COOKIE_NAME)


def set_csrf_cookie(response: Response, seed: str, max_age: int) -> None:
    """Set the CSRF seed cookie on *response*.

    The cookie mirrors the refresh-token cookie's security attributes
    (``HttpOnly``, ``SameSite=Lax``, ``Secure`` derived from scheme).

    Args:
        response: The outgoing FastAPI/Starlette response.
        seed: The random seed to store in the cookie.
        max_age: Cookie lifetime in seconds.

    """
    settings = get_settings()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=seed,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=CSRF_COOKIE_SAMESITE,
        domain=settings.cookie_domain,
        path=CSRF_COOKIE_PATH,
    )


def clear_csrf_cookie(response: Response) -> None:
    """Expire / delete the CSRF cookie on *response*.

    Args:
        response: The outgoing FastAPI/Starlette response.

    """
    settings = get_settings()
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=CSRF_COOKIE_SAMESITE,
        domain=settings.cookie_domain,
        path=CSRF_COOKIE_PATH,
    )
