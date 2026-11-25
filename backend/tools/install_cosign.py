"""Install the checksum-pinned Cosign binary from Hermeto or its upstream release."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

_RELEASE = "v3.1.4"
_ARTIFACTS = {
    "amd64": "424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa",
    "arm64": "ade83b7aac62e131cacfe96d958948b2150cc9efec46a570a2649b8e27dedad2",
}


def main() -> None:
    """Install a verified release asset in /usr/local/bin."""
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if architecture is None:
        raise SystemExit(f"Unsupported Cosign architecture: {platform.machine()}")

    filename = f"cosign-linux-{architecture}"
    expected_digest = _ARTIFACTS[architecture]
    cached_artifact = Path("/cachi2/output/deps/generic") / filename
    if os.environ.get("PIP_FIND_LINKS"):
        if not cached_artifact.is_file():
            raise SystemExit(f"Hermeto-prefetched Cosign artifact is missing: {cached_artifact}")
        source = cached_artifact
    else:
        source = Path(tempfile.gettempdir()) / filename
        url = f"https://github.com/sigstore/cosign/releases/download/{_RELEASE}/{filename}"
        with urlopen(url, timeout=120) as response, source.open("wb") as output:  # noqa: S310
            shutil.copyfileobj(response, output)

    hasher = hashlib.sha256()
    with source.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected_digest:
        raise SystemExit(f"Cosign {filename} checksum mismatch")

    target = Path("/usr/local/bin/cosign")
    shutil.copyfile(source, target)
    target.chmod(0o755)


if __name__ == "__main__":
    main()
