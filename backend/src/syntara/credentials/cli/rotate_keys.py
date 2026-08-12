"""Key rotation CLI tool for credential encryption keys.

Re-encrypts all stored credentials from an old encryption key to a new one.
Runs offline — the API server should NOT be running during rotation.

Usage:
    uv run python -m syntara.credentials.cli rotate-keys --old-key <hex> --new-key <hex>
    uv run python -m syntara.credentials.cli rotate-keys --old-key <hex> --new-key <hex> --dry-run
    uv run python -m syntara.credentials.cli rotate-keys --old-key <hex> --new-key <hex> --batch-size 100
"""

import argparse
import asyncio
import enum
import hashlib
import os
import sys
from dataclasses import dataclass, field

import structlog
from sqlalchemy.exc import OperationalError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.lib.encryption import EncryptionError, SecretEncryptor, key_from_string
from syntara.core.models.secret import EncryptedSecret

logger = structlog.stdlib.get_logger(__name__)

# Module-level session factory — defaults to production AsyncSessionLocal.
# Tests can override this to use a test database session factory.
_session_factory = AsyncSessionLocal

EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_FATAL = 2


class RowStatus(enum.StrEnum):
    """Result of rotating a single EncryptedSecret row."""

    ROTATED = "rotated"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class RotationProgress:
    """Tracks key rotation progress across batches."""

    total: int = 0
    rotated: int = 0
    skipped: int = 0
    failed: int = 0
    last_processed_id: str | None = field(default=None)


def _create_encryptors(old_key_hex: str, new_key_hex: str) -> tuple[SecretEncryptor, SecretEncryptor] | None:
    """Validate keys and create encryptor pair. Returns None on validation failure."""
    try:
        old_key = key_from_string(old_key_hex, allow_insecure=True)
        new_key = key_from_string(new_key_hex)
    except ValueError:
        logger.error("Invalid key format — keys must be 64-character hex strings")  # noqa: TRY400 — avoid key material in traceback
        return None

    if old_key == new_key:
        logger.error("Old and new keys are identical — nothing to rotate")
        return None

    logger.info(
        "Key rotation direction",
        old_key_fingerprint=hashlib.sha256(old_key).hexdigest()[:16],
        new_key_fingerprint=hashlib.sha256(new_key).hexdigest()[:16],
    )

    return SecretEncryptor(old_key), SecretEncryptor(new_key)


def _rotate_single_row(
    row: EncryptedSecret,
    old_encryptor: SecretEncryptor,
    new_encryptor: SecretEncryptor,
    *,
    dry_run: bool,
) -> RowStatus:
    """Rotate a single EncryptedSecret row.

    Returns RowStatus.ROTATED on success, SKIPPED if already encrypted
    with the new key (idempotent re-run), or FAILED if neither key works.
    """
    secret_id_str = str(row.secret_id)

    try:
        decrypted = old_encryptor.decrypt_fields(row.encrypted_data, secret_id_str)
    except EncryptionError:
        # Old key failed — check if already rotated to new key
        try:
            new_encryptor.decrypt_fields(row.encrypted_data, secret_id_str)
            logger.debug("Secret already on new key, skipping", secret_id=secret_id_str)
            return RowStatus.SKIPPED
        except EncryptionError:
            logger.error(  # noqa: TRY400
                "Secret cannot be decrypted with old or new key",
                secret_id=secret_id_str,
            )
            return RowStatus.FAILED

    try:
        re_encrypted = new_encryptor.encrypt_fields(decrypted, secret_id_str)

        if dry_run:
            verify = new_encryptor.decrypt_fields(re_encrypted, secret_id_str)
            if verify != decrypted:
                logger.error("Round-trip verification failed", secret_id=secret_id_str)
                return RowStatus.FAILED
        else:
            row.encrypted_data = re_encrypted

    except EncryptionError as exc:
        logger.error("Failed to re-encrypt secret", secret_id=secret_id_str, error=str(exc))  # noqa: TRY400
        return RowStatus.FAILED

    return RowStatus.ROTATED


async def _process_rows(
    session: AsyncSession,
    old_encryptor: SecretEncryptor,
    new_encryptor: SecretEncryptor,
    batch_size: int,
    *,
    dry_run: bool,
) -> RotationProgress:
    """Fetch and process EncryptedSecret rows in paginated batches.

    Uses keyset pagination (LIMIT + WHERE id > last_id) to avoid loading
    all rows into memory at once.
    """
    progress = RotationProgress()
    last_id = None

    while True:
        stmt = select(EncryptedSecret).order_by(EncryptedSecret.id).limit(batch_size)  # type: ignore[arg-type]
        if last_id is not None:
            stmt = stmt.where(EncryptedSecret.id > last_id)
        result = await session.exec(stmt)
        rows = result.all()

        if not rows:
            break

        progress.total += len(rows)
        for row in rows:
            status = _rotate_single_row(row, old_encryptor, new_encryptor, dry_run=dry_run)
            progress.last_processed_id = str(row.id)
            last_id = row.id

            if status is RowStatus.ROTATED:
                progress.rotated += 1
            elif status is RowStatus.SKIPPED:
                progress.skipped += 1
            else:
                progress.failed += 1

        if not dry_run:
            await session.commit()
            logger.info(
                "Batch committed",
                rotated=progress.rotated,
                skipped=progress.skipped,
                failed=progress.failed,
                total=progress.total,
            )

    return progress


async def rotate_keys(
    old_key_hex: str,
    new_key_hex: str,
    batch_size: int = 50,
    *,
    dry_run: bool = False,
) -> int:
    """Re-encrypt all encrypted secrets from old key to new key.

    Args:
        old_key_hex: Current 64-char hex encryption key.
        new_key_hex: New 64-char hex encryption key.
        batch_size: Number of rows to process per commit.
        dry_run: If True, verify decryption/re-encryption without writing to DB.

    Returns:
        Exit code: 0 success, 1 partial failure, 2 fatal error.

    """
    encryptors = _create_encryptors(old_key_hex, new_key_hex)
    if not encryptors:
        return EXIT_FATAL

    old_encryptor, new_encryptor = encryptors
    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("Starting key rotation", mode=mode, batch_size=batch_size)

    try:
        async with _session_factory() as session:
            progress = await _process_rows(session, old_encryptor, new_encryptor, batch_size, dry_run=dry_run)
    except OperationalError:
        logger.exception("Cannot connect to database — verify APP_DATABASE_URL and DB status")
        return EXIT_FATAL

    if progress.total == 0:
        logger.info("No encrypted secrets found — nothing to rotate")
        return EXIT_SUCCESS

    logger.info(
        "Key rotation complete",
        mode=mode,
        total=progress.total,
        rotated=progress.rotated,
        skipped=progress.skipped,
        failed=progress.failed,
        last_processed_id=progress.last_processed_id,
    )

    if progress.failed > 0:
        logger.warning("Some secrets failed to rotate — re-run after fixing issues", failed=progress.failed)
        return EXIT_PARTIAL_FAILURE

    return EXIT_SUCCESS


def main() -> None:
    """CLI entry point for key rotation."""
    parser = argparse.ArgumentParser(
        description="Rotate credential encryption keys. Run offline (API server stopped).",
    )
    parser.add_argument("--old-key", help="Current key (or set APP_OLD_ENCRYPTION_KEY env var)")
    parser.add_argument("--new-key", help="New key (or set APP_NEW_ENCRYPTION_KEY env var)")
    parser.add_argument("--batch-size", type=int, default=50, help="Rows per commit batch (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Verify without writing to DB")

    args = parser.parse_args()
    old_key = args.old_key or os.environ.get("APP_OLD_ENCRYPTION_KEY")
    new_key = args.new_key or os.environ.get("APP_NEW_ENCRYPTION_KEY")
    if not old_key or not new_key:
        parser.error("Provide keys via --old-key/--new-key or APP_OLD_ENCRYPTION_KEY/APP_NEW_ENCRYPTION_KEY env vars")

    exit_code = asyncio.run(
        rotate_keys(
            old_key_hex=old_key,
            new_key_hex=new_key,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        ),
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
