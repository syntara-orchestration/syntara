#!/usr/bin/env python3
"""Verify test directory structure matches source code domains.

This pre-commit hook ensures:
1. Test directories in tests/unit/ and tests/integration/ match src/syntara/ domains
2. No orphaned test directories (tests without corresponding source domain)
3. Enforces domain-driven structure documented in docs/standards/testing.md

Exit codes:
0 - All checks passed
1 - Structural violations found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

SEPARATOR = "=" * 70
DASH_SEPARATOR = "-" * 70

# Configuration: Test directories to skip validation (temporarily)
# Once these directories are reorganized to match source domains, remove them from this set
# NOTE: performance will be validated once they are reorganized by domain
# - performance: Skip (may be migrated to separate repository)
SKIP_VALIDATION = {
    "performance",
}

# ANSI escape sequence pattern (CSI sequences)
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def sanitize_for_terminal(text: str) -> str:
    """Sanitize text for terminal output by removing ANSI escape sequences.

    This prevents terminal injection attacks where malicious ANSI codes
    in directory names could affect terminal behavior.
    """
    return ANSI_ESCAPE_PATTERN.sub("", text)


def get_domains(directory: Path) -> set[str]:
    """Get all domain directories from a directory."""
    if not directory.exists():
        return set()

    return {
        item.name
        for item in directory.iterdir()
        if item.is_dir() and not item.name.startswith("_") and not item.name.startswith(".")
    }


def check_orphaned_directories(
    test_type: str,
    test_domains: set[str],
    source_domains: set[str],
    allowed_test_only: set[str],
    *,
    skip_validation: bool,
) -> tuple[list[str], list[str]]:
    """Check for orphaned test directories and generate errors/warnings.

    Returns:
        (errors, warnings) tuple

    """
    errors = []
    warnings = []

    if skip_validation:
        if test_domains:
            warnings.append(f"Skipping validation for tests/{test_type}/ (SKIP_VALIDATION enabled)")
        return errors, warnings

    orphans = test_domains - source_domains - allowed_test_only
    if orphans:
        orphan_list = "\n".join(f"  - {sanitize_for_terminal(name)}" for name in sorted(orphans))
        errors.append(f"Orphaned {test_type} test directories (no matching source domain):\n{orphan_list}")

    return errors, warnings


def check_root_level_test_files(
    test_type: str,
    test_path: Path,
    allowed_root_files: set[str],
) -> list[str]:
    """Check for test files at root of test directory.

    Returns:
        List of error messages (empty if no violations)

    """
    errors = []

    # Skip if test directory doesn't exist
    if not test_path.exists():
        return errors

    try:
        root_test_files = []
        for item in test_path.iterdir():
            # Skip directories
            try:
                if not item.is_file():
                    continue
            except OSError:
                # Skip items we can't check (broken symlinks, etc)
                continue

            # Check if it's a test file
            name = item.name
            if name.startswith("test_") and name.endswith(".py"):
                root_test_files.append(name)

    except (OSError, PermissionError):
        # If we can't read the directory, skip silently
        return errors

    # Filter out allowed files
    disallowed_root_files = [f for f in root_test_files if f not in allowed_root_files]

    if disallowed_root_files:
        file_list = "\n".join(f"  - {sanitize_for_terminal(name)}" for name in sorted(disallowed_root_files))
        errors.append(
            f"Test files found at tests/{test_type}/ root (must be in domain directories):\n{file_list}\n"
            f"Move to: tests/{test_type}/<domain>/test_*.py"
        )

    return errors


def format_error_block(title: str, items: list[str], fix_options: list[str] | None = None) -> str:
    """Format an error block matching the project's error output style."""
    lines = [
        f"\n{SEPARATOR}",
        f"{RED}{BOLD}{title}{RESET}",
        SEPARATOR,
        "",
    ]

    count = len(items)
    noun = "issue" if count == 1 else "issues"
    lines.append(f"Found {count} {noun}:")
    lines.append("")

    for i, item in enumerate(items):
        if i > 0:
            lines.append("")  # Blank line between items
        lines.append(item)

    if fix_options:
        lines.append("")
        lines.append(DASH_SEPARATOR)
        lines.append("How to fix:")
        lines.append("")
        for i, option in enumerate(fix_options, 1):
            lines.append(f"  Option {i}: {option}")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)


def verify_test_structure(repo_root: Path) -> tuple[bool, list[str], list[str]]:
    """Verify test structure matches source code domains.

    Returns:
        (success, errors, warnings) tuple

    """
    errors = []
    warnings = []

    src_dir = repo_root / "src" / "syntara"
    source_domains = get_domains(src_dir)

    # Test directories configuration: name -> (path, skip_validation)
    test_dirs_config = {
        "unit": (repo_root / "tests" / "unit", False),
        "integration": (repo_root / "tests" / "integration", False),
        "e2e": (repo_root / "tests" / "e2e", "e2e" in SKIP_VALIDATION),
        "performance": (repo_root / "tests" / "performance", "performance" in SKIP_VALIDATION),
    }

    # Get domains for each test directory
    test_dirs = {name: (path, get_domains(path), skip) for name, (path, skip) in test_dirs_config.items()}

    # Allow-list for test directories without a matching source domain.
    # Infrastructure dirs and cross-cutting test dirs that group tests
    # by concern rather than by source domain.
    allowed_test_only = {
        "__pycache__",
        "helpers",
        "fixtures",
        "agents",
        "cli",
        "models",
        "services",
        "tls",
        "tools",
        "utils",
        "validators",
        "websocket",
        "workflow",
    }

    # These source domains are allowed to have no tests
    allowed_no_tests = {
        "example",  # Example code, no tests needed
        "seed",  # Seed data, no tests needed
        "__pycache__",
    }

    # Check for orphaned test directories
    for test_type, (_, test_domains, skip_validation) in test_dirs.items():
        dir_errors, dir_warnings = check_orphaned_directories(
            test_type, test_domains, source_domains, allowed_test_only, skip_validation=skip_validation
        )
        errors.extend(dir_errors)
        warnings.extend(dir_warnings)

    # Check for root-level test files (all tests must be in domain directories)
    # Allow-list for specific files that are exceptions
    allowed_root_files = {
        "e2e": {"test_settings_endpoints.py"},  # Settings endpoints test stays at root
    }

    for test_type, (test_path, _, skip_validation) in test_dirs.items():
        if skip_validation:
            continue

        file_errors = check_root_level_test_files(
            test_type,
            test_path,
            allowed_root_files.get(test_type, set()),
        )
        errors.extend(file_errors)

    # Informational: source domains without tests (not an error, just FYI)
    all_test_domains = {domain for _, domains, _ in test_dirs.values() for domain in domains}
    untested_domains = source_domains - all_test_domains - allowed_no_tests
    if untested_domains:
        sanitized_domains = ", ".join(sanitize_for_terminal(d) for d in sorted(untested_domains))
        warnings.append(f"Source domains without tests: {sanitized_domains} (OK - not all domains require tests)")

    return len(errors) == 0, errors, warnings


def main() -> int:
    """Run test structure verification."""
    repo_root = Path(__file__).parent.parent.parent

    success, errors, warnings = verify_test_structure(repo_root)

    # Print warnings first (informational)
    if warnings:
        sys.stdout.write(f"\n{YELLOW}Informational:{RESET}\n")
        for warning in warnings:
            sys.stdout.write(f"{warning}\n")

    if success:
        sys.stdout.write(
            f"{GREEN}SUCCESS{RESET}: Test directory structure is valid\n  • All test directories match source domains\n"
        )
        return 0

    # Format and print errors
    error_block = format_error_block(
        "Test Structure Validation Failed",
        errors,
        fix_options=[
            "Move orphaned test directories to match a domain in src/syntara/",
            "Consult docs/standards/testing.md for domain organization rules",
        ],
    )
    sys.stderr.write(error_block + "\n")

    sys.stderr.write(f"\n{RED}FAILED{RESET}: {len(errors)} test structure validation error(s)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
