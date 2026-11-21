"""Filter requirements.txt hashes to only include target build platforms.

Hermeto downloads ALL artifacts matching ANY hash in requirements.txt,
regardless of platform. This means macOS, Windows, PyPy, and free-threaded
Python wheels are needlessly downloaded for Linux-only Konflux builds.

This script reads uv.lock to map hashes to filenames, then rewrites
requirements.txt keeping only hashes for the target platforms.

For hashes not found in uv.lock (e.g. build dependencies in
requirements-build.txt), the script queries the PyPI JSON API to resolve
hash-to-filename mappings.

Usage:
    python tools/ci/filter_requirements_hashes.py [--lock uv.lock] [requirements.txt]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ALLOWED_PLATFORM_PATTERNS = re.compile(
    r"("
    r"py3-none-any|py2\.py3-none-any"  # pure Python
    r"|none-any"  # other pure Python variants
    r"|cp31[23]-cp31[23]-manylinux[_0-9]*_(x86_64|aarch64)"  # CPython manylinux
    r"|cp31[23]-cp31[23]-musllinux[_0-9]*_(x86_64|aarch64)"  # CPython musllinux
    r"|cp3[0-9]+-abi3-manylinux[_0-9]*_(x86_64|aarch64)"  # stable ABI manylinux (any base CPython)
    r"|cp3[0-9]+-abi3-musllinux[_0-9]*_(x86_64|aarch64)"  # stable ABI musllinux (any base CPython)
    r")"
)

SDIST_EXTENSIONS = (".tar.gz", ".zip")
MIN_WHEEL_PARTS = 4


def parse_uv_lock(lock_path: Path) -> dict[str, str]:
    """Build a hash -> filename mapping from uv.lock."""
    hash_to_filename: dict[str, str] = {}
    content = lock_path.read_text()

    for match in re.finditer(r'url\s*=\s*"([^"]+)",\s*hash\s*=\s*"sha256:([a-f0-9]+)"', content):
        url, sha = match.group(1), match.group(2)
        filename = url.rsplit("/", 1)[-1]
        hash_to_filename[sha] = filename

    return hash_to_filename


def _query_pypi(name: str, version: str) -> dict[str, str]:
    """Query PyPI JSON API for hash -> filename mapping of a release."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except (OSError, ValueError) as exc:
        print(f"  Warning: PyPI lookup failed for {name}=={version}: {exc}", file=sys.stderr)
        return {}

    mapping: dict[str, str] = {}
    for file_info in data.get("urls", []):
        digests = file_info.get("digests", {})
        sha256 = digests.get("sha256")
        filename = file_info.get("filename")
        if sha256 and filename:
            mapping[sha256] = filename
    return mapping


def _extract_packages(req_path: Path) -> list[tuple[str, str]]:
    """Extract (name, version) pairs from a requirements.txt file."""
    packages: list[tuple[str, str]] = []
    for line in req_path.read_text().splitlines():
        m = re.match(r"^([a-zA-Z0-9_.-]+)==([a-zA-Z0-9_.]+)", line)
        if m:
            packages.append((m.group(1), m.group(2)))
    return packages


def resolve_hashes_via_pypi(
    req_path: Path,
    hash_to_filename: dict[str, str],
) -> None:
    """Enrich hash_to_filename with PyPI data for packages with unresolved hashes."""
    lines = req_path.read_text().splitlines()
    unresolved_pkgs: dict[str, tuple[str, str]] = {}
    current_pkg: tuple[str, str] | None = None

    for line in lines:
        m = re.match(r"^([a-zA-Z0-9_.-]+)==([a-zA-Z0-9_.]+)", line)
        if m:
            current_pkg = (m.group(1), m.group(2))

        sha_m = re.search(r"--hash=sha256:([a-f0-9]+)", line)
        if sha_m and current_pkg and sha_m.group(1) not in hash_to_filename:
            key = f"{current_pkg[0]}=={current_pkg[1]}"
            unresolved_pkgs[key] = current_pkg

    if not unresolved_pkgs:
        return

    print(
        f"Querying PyPI for {len(unresolved_pkgs)} packages not in uv.lock...",
        file=sys.stderr,
    )
    for _key, (name, version) in sorted(unresolved_pkgs.items()):
        pypi_mapping = _query_pypi(name, version)
        hash_to_filename.update(pypi_mapping)


def is_allowed(filename: str) -> bool:
    """Check if a wheel filename matches the target build platforms."""
    if any(filename.endswith(ext) for ext in SDIST_EXTENSIONS):
        return True

    if not filename.endswith(".whl"):
        return True

    parts = filename.rsplit("-", 3)
    if len(parts) < MIN_WHEEL_PARTS:
        return True

    platform_tag = "-".join(parts[-3:]).removesuffix(".whl")
    return bool(ALLOWED_PLATFORM_PATTERNS.search(platform_tag))


def _collect_hash_block(
    lines: list[str], start: int, hash_to_filename: dict[str, str]
) -> tuple[list[tuple[str, str | None]], int]:
    """Collect consecutive --hash= lines into a block with resolved filenames."""
    block: list[tuple[str, str | None]] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("--hash="):
        hash_line = lines[i]
        sha_match = re.search(r"--hash=sha256:([a-f0-9]+)", hash_line)
        filename = hash_to_filename.get(sha_match.group(1)) if sha_match else None
        block.append((hash_line, filename))
        i += 1
    return block, i


def _filter_hash_block(
    hash_block: list[tuple[str, str | None]],
) -> tuple[list[str], int, int]:
    """Keep only hashes for allowed platforms, returning (kept_lines, kept, unknown)."""
    kept: list[str] = []
    unknown = 0
    for hash_line, filename in hash_block:
        if filename is None:
            kept.append(hash_line)
            unknown += 1
        elif is_allowed(filename):
            kept.append(hash_line)

    if not kept and hash_block:
        kept.append(hash_block[0][0])

    if len(kept) == 1:
        last = kept[0].rstrip()
        if last.endswith(" \\"):
            kept[0] = last[:-2] + "\n"

    return kept, len(kept), unknown


def filter_requirements(req_path: Path, hash_to_filename: dict[str, str]) -> str:
    """Filter requirements.txt to only keep hashes for allowed platforms."""
    lines = req_path.read_text().splitlines(keepends=True)
    output: list[str] = []
    total_hashes = 0
    kept_hashes = 0
    unknown_hashes = 0

    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith("--hash="):
            output.append(lines[i])
            i += 1
            continue

        hash_block, i = _collect_hash_block(lines, i, hash_to_filename)
        total_hashes += len(hash_block)
        kept, count, unknown = _filter_hash_block(hash_block)
        kept_hashes += count
        unknown_hashes += unknown
        output.extend(kept)

    print(
        f"Filtered requirements.txt: {kept_hashes}/{total_hashes} hashes kept ({unknown_hashes} unresolved)",
        file=sys.stderr,
    )

    return "".join(output)


def main() -> None:
    """CLI entry point for filtering requirements.txt hashes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "requirements",
        nargs="?",
        default="requirements.txt",
        help="Path to requirements.txt (default: requirements.txt)",
    )
    parser.add_argument(
        "--lock",
        default="uv.lock",
        help="Path to uv.lock (default: uv.lock)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout instead of overwriting the file",
    )
    args = parser.parse_args()

    lock_path = Path(args.lock)
    req_path = Path(args.requirements)

    if not lock_path.exists():
        print(f"Error: {lock_path} not found", file=sys.stderr)
        sys.exit(1)
    if not req_path.exists():
        print(f"Error: {req_path} not found", file=sys.stderr)
        sys.exit(1)

    hash_to_filename = parse_uv_lock(lock_path)
    resolve_hashes_via_pypi(req_path, hash_to_filename)
    filtered = filter_requirements(req_path, hash_to_filename)

    if args.dry_run:
        sys.stdout.write(filtered)
    else:
        req_path.write_text(filtered)


if __name__ == "__main__":
    main()
