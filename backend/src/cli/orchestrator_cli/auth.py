"""Persistent token storage for the Automation Orchestrator CLI.

Tokens are stored per-instance under ``~/.orchestrator/``.  Each instance
(base URL) gets its own JSON file, keyed by a URL-safe slug derived from the
URL so that ``http://localhost:8000`` and ``https://prod.example.com``
never collide.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from .benchmark import note, phase

_CONFIG_DIR = Path.home() / ".orchestrator"


def _instance_slug(base_url: str) -> str:
    """Deterministic, filesystem-safe slug for a base URL."""
    parsed = urlparse(base_url)
    label = f"{parsed.hostname}_{parsed.port or 443}"
    digest = hashlib.sha256(base_url.encode()).hexdigest()[:8]
    return f"{label}_{digest}"


def _token_path(base_url: str) -> Path:
    return _CONFIG_DIR / f"{_instance_slug(base_url)}.json"


def save_token(base_url: str, access_token: str, expires_in: int | None = None) -> Path:
    """Persist a token for the given instance. Returns the file path."""
    with phase("auth.save_token"):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        saved_at = time.time()
        data: dict[str, object] = {
            "base_url": base_url,
            "access_token": access_token,
            "saved_at": saved_at,
        }
        if expires_in is not None:
            data["expires_at"] = saved_at + expires_in
        path = _token_path(base_url)
        path.write_text(json.dumps(data, indent=2) + "\n")
        path.chmod(0o600)
        return path


def load_token(base_url: str) -> str | None:
    """Return a cached token for *base_url*, or ``None`` if missing/expired."""
    with phase("auth.load_token"):
        path = _token_path(base_url)
        if not path.exists():
            note("token_source", "missing")
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            note("token_source", "invalid_cache")
            return None
        expires_at = data.get("expires_at")
        if expires_at is not None and time.time() >= expires_at:
            path.unlink(missing_ok=True)
            note("token_source", "expired")
            return None
        token = data.get("access_token")
        note("token_source", "cache")
        return str(token) if token is not None else None


def clear_token(base_url: str) -> bool:
    """Remove the cached token for *base_url*. Returns True if a file was deleted."""
    path = _token_path(base_url)
    if path.exists():
        path.unlink()
        return True
    return False
