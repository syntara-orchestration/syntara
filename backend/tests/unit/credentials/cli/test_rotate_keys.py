"""Tests for key rotation CLI tool (T079)."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import SecretEncryptor
from syntara.credentials.cli.rotate_keys import (
    EXIT_FATAL,
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    RotationProgress,
    RowStatus,
    _create_encryptors,
    _rotate_single_row,
    rotate_keys,
)
from tests.fixtures.encryption import (
    NEW_KEY,
    NEW_KEY_HEX,
    OLD_KEY,
    OLD_KEY_HEX,
    WRONG_KEY,
    ZEROS_KEY_HEX,
)


def _make_encrypted_row(old_encryptor: SecretEncryptor) -> MagicMock:
    """Create a mock EncryptedSecret row with real encrypted data."""
    secret_id = uuid4()
    row = MagicMock()
    row.id = uuid4()
    row.secret_id = secret_id
    row.encrypted_data = old_encryptor.encrypt_fields(
        {"token": "secret-value", "host": "example.com"},
        str(secret_id),
    )
    return row


class TestCreateEncryptors:
    """Tests for _create_encryptors validation."""

    def test_valid_keys_return_encryptor_pair(self) -> None:
        result = _create_encryptors(OLD_KEY_HEX, NEW_KEY_HEX)
        assert result is not None
        old_enc, new_enc = result
        assert isinstance(old_enc, SecretEncryptor)
        assert isinstance(new_enc, SecretEncryptor)

    def test_invalid_old_key_returns_none(self) -> None:
        result = _create_encryptors("not-a-hex-key", NEW_KEY_HEX)
        assert result is None

    def test_invalid_new_key_returns_none(self) -> None:
        result = _create_encryptors(OLD_KEY_HEX, "short")
        assert result is None

    def test_identical_keys_returns_none(self) -> None:
        result = _create_encryptors(OLD_KEY_HEX, OLD_KEY_HEX)
        assert result is None

    def test_all_zeros_old_key_accepted(self) -> None:
        """Rotation FROM the legacy all-zeros default key must be allowed."""
        result = _create_encryptors(ZEROS_KEY_HEX, NEW_KEY_HEX)
        assert result is not None

    def test_all_zeros_new_key_rejected(self) -> None:
        """Rotation TO the all-zeros key must be rejected."""
        result = _create_encryptors(OLD_KEY_HEX, ZEROS_KEY_HEX)
        assert result is None

    def test_logs_key_fingerprints(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify key fingerprints are logged so operators can confirm direction."""
        import logging

        with caplog.at_level(logging.INFO):
            result = _create_encryptors(OLD_KEY_HEX, NEW_KEY_HEX)

        assert result is not None
        expected_old_fp = hashlib.sha256(OLD_KEY).hexdigest()[:16]
        assert any(expected_old_fp in record.message for record in caplog.records) or any(
            expected_old_fp in str(getattr(record, "old_key_fingerprint", "")) for record in caplog.records
        )
        fingerprint_record = next(
            (r for r in caplog.records if "Key rotation direction" in r.message),
            None,
        )
        assert fingerprint_record is not None


class TestRotateSingleRow:
    """Tests for _rotate_single_row."""

    def test_successful_rotation(self) -> None:
        old_enc = SecretEncryptor(OLD_KEY)
        new_enc = SecretEncryptor(NEW_KEY)
        row = _make_encrypted_row(old_enc)

        result = _rotate_single_row(row, old_enc, new_enc, dry_run=False)

        assert result is RowStatus.ROTATED
        decrypted = new_enc.decrypt_fields(row.encrypted_data, str(row.secret_id))
        assert decrypted["token"] == "secret-value"  # noqa: S105
        assert decrypted["host"] == "example.com"

    def test_dry_run_does_not_modify_row(self) -> None:
        old_enc = SecretEncryptor(OLD_KEY)
        new_enc = SecretEncryptor(NEW_KEY)
        row = _make_encrypted_row(old_enc)
        original_data = dict(row.encrypted_data)

        result = _rotate_single_row(row, old_enc, new_enc, dry_run=True)

        assert result is RowStatus.ROTATED
        assert row.encrypted_data == original_data

    def test_already_rotated_row_is_skipped(self) -> None:
        """Row encrypted with new key is detected and skipped (idempotent)."""
        old_enc = SecretEncryptor(OLD_KEY)
        new_enc = SecretEncryptor(NEW_KEY)

        secret_id = uuid4()
        row = MagicMock()
        row.id = uuid4()
        row.secret_id = secret_id
        row.encrypted_data = new_enc.encrypt_fields(
            {"token": "already-rotated"},
            str(secret_id),
        )

        result = _rotate_single_row(row, old_enc, new_enc, dry_run=False)
        assert result is RowStatus.SKIPPED

    def test_neither_key_works_returns_failed(self) -> None:
        """Row encrypted with an unknown third key is reported as failed."""
        old_enc = SecretEncryptor(OLD_KEY)
        new_enc = SecretEncryptor(NEW_KEY)

        third_enc = SecretEncryptor(WRONG_KEY)

        secret_id = uuid4()
        row = MagicMock()
        row.id = uuid4()
        row.secret_id = secret_id
        row.encrypted_data = third_enc.encrypt_fields(
            {"token": "unknown-key"},
            str(secret_id),
        )

        result = _rotate_single_row(row, old_enc, new_enc, dry_run=False)
        assert result is RowStatus.FAILED


def _mock_paginated_session(rows: list[MagicMock]) -> tuple[MagicMock, AsyncMock]:
    """Create a mock session that returns rows on first exec, empty on second (pagination)."""
    mock_session = AsyncMock()
    first_result = MagicMock()
    first_result.all.return_value = rows
    empty_result = MagicMock()
    empty_result.all.return_value = []
    mock_session.exec = AsyncMock(side_effect=[first_result, empty_result])
    mock_session.commit = AsyncMock()
    return mock_session, mock_session.commit


class TestRotateKeys:
    """Tests for the main rotate_keys async function."""

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_happy_path(self, mock_session_local: MagicMock) -> None:
        """All rows rotated successfully."""
        old_enc = SecretEncryptor(OLD_KEY)
        rows = [_make_encrypted_row(old_enc) for _ in range(3)]

        mock_session, mock_commit = _mock_paginated_session(rows)
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, batch_size=50)

        assert exit_code == EXIT_SUCCESS
        mock_commit.assert_called()

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_dry_run_no_commits(self, mock_session_local: MagicMock) -> None:
        """Dry run verifies round-trip without committing."""
        old_enc = SecretEncryptor(OLD_KEY)
        rows = [_make_encrypted_row(old_enc) for _ in range(2)]

        mock_session, mock_commit = _mock_paginated_session(rows)
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, dry_run=True)

        assert exit_code == EXIT_SUCCESS
        mock_commit.assert_not_called()

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_empty_db(self, mock_session_local: MagicMock) -> None:
        """No rows to process returns success."""
        mock_session, _ = _mock_paginated_session([])
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX)
        assert exit_code == EXIT_SUCCESS

    @pytest.mark.asyncio
    async def test_invalid_old_key_returns_fatal(self) -> None:
        exit_code = await rotate_keys("invalid", NEW_KEY_HEX)
        assert exit_code == EXIT_FATAL

    @pytest.mark.asyncio
    async def test_identical_keys_returns_fatal(self) -> None:
        exit_code = await rotate_keys(OLD_KEY_HEX, OLD_KEY_HEX)
        assert exit_code == EXIT_FATAL

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_partial_failure(self, mock_session_local: MagicMock) -> None:
        """Some rows fail, others succeed — returns partial failure."""
        old_enc = SecretEncryptor(OLD_KEY)
        good_row = _make_encrypted_row(old_enc)

        # Bad row has data encrypted with a different key
        bad_row = MagicMock()
        bad_row.id = uuid4()
        bad_row.secret_id = uuid4()
        bad_row.encrypted_data = {"token": "not-valid-ciphertext"}

        mock_session, _ = _mock_paginated_session([good_row, bad_row])
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, batch_size=10)
        assert exit_code == EXIT_PARTIAL_FAILURE

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_batch_commits(self, mock_session_local: MagicMock) -> None:
        """Pagination: each batch fetched and committed separately."""
        old_enc = SecretEncryptor(OLD_KEY)
        batch1 = [_make_encrypted_row(old_enc) for _ in range(2)]
        batch2 = [_make_encrypted_row(old_enc) for _ in range(2)]

        mock_session = AsyncMock()
        r1 = MagicMock()
        r1.all.return_value = batch1
        r2 = MagicMock()
        r2.all.return_value = batch2
        r_empty = MagicMock()
        r_empty.all.return_value = []
        mock_session.exec = AsyncMock(side_effect=[r1, r2, r_empty])
        mock_session.commit = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, batch_size=2)

        assert exit_code == EXIT_SUCCESS
        # 2 batches of 2 rows each → 2 commits
        assert mock_session.commit.call_count == 2


class TestIdempotentReRun:
    """Tests for idempotent re-run behavior (already-rotated credentials)."""

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_all_already_rotated_returns_success(self, mock_session_local: MagicMock) -> None:
        """Re-running rotation when all rows are already on new key returns success."""
        new_enc = SecretEncryptor(NEW_KEY)

        rows = []
        for _ in range(3):
            secret_id = uuid4()
            row = MagicMock()
            row.id = uuid4()
            row.secret_id = secret_id
            row.encrypted_data = new_enc.encrypt_fields(
                {"token": "already-rotated"},
                str(secret_id),
            )
            rows.append(row)

        mock_session, _mock_commit = _mock_paginated_session(rows)
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, batch_size=50)

        assert exit_code == EXIT_SUCCESS

    @pytest.mark.asyncio
    @patch("syntara.credentials.cli.rotate_keys._session_factory")
    async def test_mixed_rotated_and_pending_returns_success(self, mock_session_local: MagicMock) -> None:
        """Interrupted rotation recovery: mix of old-key and new-key rows returns success."""
        old_enc = SecretEncryptor(OLD_KEY)
        new_enc = SecretEncryptor(NEW_KEY)

        pending_row = _make_encrypted_row(old_enc)

        already_done_id = uuid4()
        already_done_row = MagicMock()
        already_done_row.id = uuid4()
        already_done_row.secret_id = already_done_id
        already_done_row.encrypted_data = new_enc.encrypt_fields(
            {"token": "already-rotated"},
            str(already_done_id),
        )

        mock_session, _ = _mock_paginated_session([pending_row, already_done_row])
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await rotate_keys(OLD_KEY_HEX, NEW_KEY_HEX, batch_size=50)

        assert exit_code == EXIT_SUCCESS


class TestRotationProgress:
    """Tests for RotationProgress dataclass."""

    def test_defaults(self) -> None:
        progress = RotationProgress()
        assert progress.total == 0
        assert progress.rotated == 0
        assert progress.skipped == 0
        assert progress.failed == 0
        assert progress.last_processed_id is None
