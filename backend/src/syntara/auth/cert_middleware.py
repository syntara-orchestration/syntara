"""ASGI middleware for mTLS client certificate authentication.

Extracts the client certificate CN from the ASGI scope (injected by
the TLS protocol subclass) and stores it in the scope state. Gates
trust of the ``X-On-Behalf-Of`` header to cert-authenticated requests
only. Actor context for audit is handled by the audit middleware,
which reads from the scope state set here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cryptography import x509

from syntara.api.constants import EXCLUDED_PATH_PREFIXES, EXCLUDED_PATHS
from syntara.core.config.base import get_settings

logger = logging.getLogger(__name__)

_ON_BEHALF_OF_HEADER = b"x-on-behalf-of"


class CertificateValidationError(Exception):
    """Raised when a client certificate fails post-handshake validation."""

    def __init__(self, reason: str, detail: str) -> None:  # noqa: D107
        self.reason = reason
        self.detail = detail
        super().__init__(detail)


def _extract_cn(peercert: dict[str, Any]) -> str | None:
    """Extract the Common Name from a parsed peer certificate dict."""
    for rdn in peercert.get("subject", ()):
        for attr_type, attr_value in rdn:
            if attr_type == "commonName":
                return str(attr_value)
    return None


def _load_revoked_serials(crl_path: str) -> frozenset[int]:
    """Load revoked certificate serial numbers from a PEM-encoded CRL file."""
    crl_pem = Path(crl_path).read_bytes()
    crl = x509.load_pem_x509_crl(crl_pem)
    return frozenset(revoked.serial_number for revoked in crl)


def _validate_client_cert(
    peercert: dict[str, Any],
    *,
    revoked_serials: frozenset[int] | None,
) -> str:
    """Extract and validate a client certificate's CN and revocation status.

    Returns the CN on success, raises CertificateValidationError on failure.
    Allowlist checking is handled by the middleware to distinguish between
    hard rejection (revoked cert) and soft fallthrough (untrusted CN).
    """
    cn = _extract_cn(peercert)
    if cn is None:
        raise CertificateValidationError(
            reason="missing_cn",
            detail="Client certificate has no Common Name",
        )

    if revoked_serials is not None:
        serial = int(peercert["serialNumber"], 16)
        if serial in revoked_serials:
            raise CertificateValidationError(
                reason="certificate_revoked",
                detail=f"Client certificate serial {peercert['serialNumber']} has been revoked",
            )

    return cn


async def _send_403(send: Any, detail: str) -> None:  # noqa: ANN401
    """Send a raw ASGI 403 response with RFC 9457 problem+json body."""
    body = json.dumps(
        {
            "type": "https://api.example.com/errors/certificate-validation-failed",
            "title": "Certificate Validation Failed",
            "status": 403,
            "detail": detail,
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                [b"content-type", b"application/problem+json"],
                [b"content-length", str(len(body)).encode()],
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ClientCertAuthMiddleware:
    """Authenticate internal service requests via mTLS client certificate.

    When S2S TLS is disabled, this middleware is a no-op.  When enabled,
    it extracts the client cert CN from ``scope["extensions"]["tls"]``
    (populated by the TLS protocol subclass) and stores it in
    ``scope["state"]`` for downstream middleware and dependencies.
    """

    def __init__(self, app: Any) -> None:  # noqa: ANN401, D107
        self.app = app
        settings = get_settings()
        self._tls_enabled = settings.s2s_tls_enabled
        self._cn_allowlist: frozenset[str] | None = (
            frozenset(settings.s2s_tls_cn_allowlist) if settings.s2s_tls_cn_allowlist is not None else None
        )
        self._revoked_serials: frozenset[int] | None = (
            _load_revoked_serials(settings.s2s_tls_crl_path) if settings.s2s_tls_crl_path is not None else None
        )
        if self._tls_enabled and self._cn_allowlist is not None:
            from syntara.core.models.principal import KNOWN_SERVICE_CNS  # noqa: PLC0415

            missing = set(KNOWN_SERVICE_CNS) - self._cn_allowlist
            if missing:
                logger.warning(
                    "KNOWN_SERVICE_CNS entries missing from APP_S2S_TLS_CN_ALLOWLIST: %s — "
                    "these services will authenticate via TLS but not receive service identity",
                    ", ".join(sorted(missing)),
                )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401, D102
        if scope["type"] != "http" or not self._tls_enabled:
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        # The peercert is already CA-verified by the TLS handshake when present.
        peercert = scope.get("extensions", {}).get("tls", {}).get("peercert")

        cert_cn = None
        is_service = False

        if peercert:
            try:
                cert_cn = _validate_client_cert(
                    peercert,
                    revoked_serials=self._revoked_serials,
                )
            except CertificateValidationError as exc:
                logger.warning("Client certificate rejected: %s", exc.detail)
                await _send_403(send, exc.detail)
                return

            is_service = self._cn_allowlist is not None and cert_cn in self._cn_allowlist
            if not is_service:
                logger.debug("Client certificate CN '%s' not in allowlist; treating as proxy", cert_cn)
                cert_cn = None

        state["is_cert_authenticated"] = is_service
        state["cert_cn"] = cert_cn

        if not is_service:
            self._strip_header(scope, _ON_BEHALF_OF_HEADER)

        await self.app(scope, receive, send)

    @staticmethod
    def _strip_header(scope: dict[str, Any], header_name: bytes) -> None:
        """Remove a header from the ASGI scope to prevent spoofing."""
        headers = scope.get("headers")
        if headers:
            scope["headers"] = [(k, v) for k, v in headers if k.lower() != header_name]
