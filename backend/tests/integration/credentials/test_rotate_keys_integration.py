"""Integration tests for credential encryption key rotation CLI tool.

Tests the full rotation workflow against a real PostgreSQL database with actual
encrypted credentials. Validates batch processing, error handling, dry-run mode,
and post-rotation API compatibility.


Related ticket: AAP-72277
"""

import asyncio
from collections.abc import Callable, Generator
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.lib.encryption import EncryptionError, SecretEncryptor
from syntara.core.models import User
from syntara.core.models.secret import EncryptedSecret
from syntara.core.services.secret_service import SecretService
from syntara.core.services.storage_backend import DatabaseBackend
from syntara.credentials.cli import rotate_keys as rotate_keys_module
from syntara.credentials.cli.rotate_keys import (
    EXIT_FATAL,
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    rotate_keys,
)
from syntara.credentials.cli.rotate_keys import (
    _session_factory as original_session_factory,
)
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from tests.fixtures.encryption import (
    NEW_KEY,
    NEW_KEY_HEX,
    OLD_KEY,
    OLD_KEY_HEX,
    WRONG_KEY,
    ZEROS_KEY,
    ZEROS_KEY_HEX,
)


@pytest.fixture(autouse=True)
def _patch_session_factory(test_session_factory) -> Generator[None, None, None]:
    """Patch rotate_keys module session factory for all tests.

    Ensures test database isolation and prevents state leakage if tests fail.
    """
    rotate_keys_module._session_factory = test_session_factory
    yield
    rotate_keys_module._session_factory = original_session_factory


async def _create_test_credential(
    session: AsyncSession,
    credential_type: CredentialType,
    project_id: str,
    inputs: dict[str, str],
    created_by_id: str,
    name: str | None = None,
) -> Credential:
    """Helper to create a test credential with encrypted inputs."""
    # Create encrypted secret using SecretService
    encryptor = SecretEncryptor(OLD_KEY)
    backend = DatabaseBackend(session)
    secret_service = SecretService(session, encryptor, backend)
    secret_id = await secret_service.create_secret(inputs)

    credential = Credential(
        name=name or f"Test Credential {uuid4().hex[:8]}",
        credential_type_id=credential_type.id,
        project_id=project_id,
        secret_id=secret_id,
        created_by=created_by_id,
    )
    session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return credential


@pytest.mark.asyncio
class TestBasicKeyRotation:
    """Test 1: Basic key rotation with 10 credentials."""

    async def test_basic_rotation_success(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify basic key rotation with 10 credentials of different types."""
        # Create 10 test credentials
        for i in range(10):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"secret-token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
                name=f"Bearer Token {i}",
            )

        # Run rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=False,
        )

        # Verify exit code
        assert exit_code == EXIT_SUCCESS

        # Verify all credentials were rotated
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        secrets = result.all()
        assert len(secrets) == 10

        # Verify all secrets can be decrypted with new key
        new_encryptor = SecretEncryptor(NEW_KEY)
        for secret in secrets:
            decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
            assert "token" in decrypted
            assert decrypted["token"].startswith("secret-token-")


@pytest.mark.asyncio
class TestLegacyZerosKeyRotation:
    """Rotate credentials encrypted with the legacy all-zeros default key."""

    async def test_rotation_from_zeros_key(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify full end-to-end rotation from the all-zeros key to a real key."""
        zeros_encryptor = SecretEncryptor(ZEROS_KEY)
        backend = DatabaseBackend(test_db_session)
        secret_service = SecretService(test_db_session, zeros_encryptor, backend)

        for i in range(5):
            secret_id = await secret_service.create_secret(
                {"token": f"legacy-token-{i}", "host": f"legacy{i}.example.com"},
            )
            credential = Credential(
                name=f"Legacy Zeros Credential {i}",
                credential_type_id=bearer_type.id,
                project_id=test_project_id,
                secret_id=secret_id,
                created_by=str(test_user.id),
            )
            test_db_session.add(credential)

        await test_db_session.commit()

        exit_code = await rotate_keys(
            old_key_hex=ZEROS_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=False,
        )

        assert exit_code == EXIT_SUCCESS

        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        secrets = result.all()
        assert len(secrets) == 5

        new_encryptor = SecretEncryptor(NEW_KEY)
        for secret in secrets:
            decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
            assert "token" in decrypted
            assert decrypted["token"].startswith("legacy-token-")


@pytest.mark.asyncio
class TestDryRunValidation:
    """Test 2: Dry-run mode validation."""

    async def test_dry_run_does_not_modify_database(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify dry-run mode previews changes without modifying database."""
        # Create 5 test credentials
        original_secrets = []
        for i in range(5):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"original-token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )

        # Capture original encrypted data
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        original_secrets = [(s.id, dict(s.encrypted_data)) for s in result.all()]

        # Run dry-run rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=True,
        )

        # Verify exit code
        assert exit_code == EXIT_SUCCESS

        # Verify database was NOT modified
        result = await test_db_session.exec(stmt)
        current_secrets = [(s.id, dict(s.encrypted_data)) for s in result.all()]

        assert len(current_secrets) == len(original_secrets)
        for (orig_id, orig_data), (curr_id, curr_data) in zip(original_secrets, current_secrets, strict=False):
            assert orig_id == curr_id
            assert orig_data == curr_data  # encrypted_data unchanged

        # Verify secrets still exist with unchanged encrypted data
        # Note: We can't easily decrypt without the actual secret_id
        # This is a limitation of the dry-run test - we verify data unchanged instead
        assert len(current_secrets) == 5


@pytest.mark.asyncio
class TestPartialFailureRecovery:
    """Test 3: Partial failure recovery with corrupted credential."""

    async def test_rotation_skips_corrupted_credential(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify rotation skips corrupted credential and continues processing."""
        # Create 10 credentials
        credentials = []
        for i in range(10):
            cred = await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )
            credentials.append(cred)

        # Corrupt credential #7 by encrypting with WRONG key
        wrong_encryptor = SecretEncryptor(WRONG_KEY)
        stmt = select(EncryptedSecret).where(EncryptedSecret.secret_id == credentials[7].secret_id)
        result = await test_db_session.exec(stmt)
        corrupted_secret = result.one()

        # Re-encrypt with wrong key (simulates corruption)
        corrupted_data = wrong_encryptor.encrypt_fields(
            {"token": "corrupted-token", "host": "corrupted.example.com"},
            str(corrupted_secret.secret_id),
        )
        corrupted_secret.encrypted_data = corrupted_data
        test_db_session.add(corrupted_secret)
        await test_db_session.commit()

        # Run rotation (should skip corrupted row)
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=False,
        )

        # Verify partial failure exit code
        assert exit_code == EXIT_PARTIAL_FAILURE

        # Verify 9 credentials rotated successfully
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        all_secrets = result.all()

        new_encryptor = SecretEncryptor(NEW_KEY)
        successful_rotations = 0
        failed_rotations = 0

        for secret in all_secrets:
            try:
                decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
                if "token" in decrypted:
                    successful_rotations += 1
            except Exception:
                failed_rotations += 1

        assert successful_rotations == 9
        assert failed_rotations == 1


@pytest.mark.asyncio
class TestLargeBatchProcessing:
    """Test 4: Large batch testing with 100+ credentials."""

    async def test_large_credential_set_rotation(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify rotation handles 150 credentials with batch size 50."""
        # Create 150 credentials
        for i in range(150):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"large-token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )

        # Run rotation with batch_size=50 (should process in 3 batches)
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=50,
            dry_run=False,
        )

        # Verify success
        assert exit_code == EXIT_SUCCESS

        # Verify all 150 credentials rotated
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        secrets = result.all()
        assert len(secrets) == 150

        # Verify all decrypt with new key
        new_encryptor = SecretEncryptor(NEW_KEY)
        for secret in secrets:
            decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
            assert "token" in decrypted


@pytest.mark.asyncio
class TestPostRotationAPIVerification:
    """Test 5: Post-rotation API compatibility."""

    @pytest.mark.skip(
        reason="Requires app restart with new key - auth_client uses old key. "
        "In production, API pods are restarted with APP_DB_ENCRYPTION_KEY set to new key."
    )
    async def test_crud_operations_work_after_rotation(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        auth_client: AsyncClient,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify credential CRUD operations work after key rotation.

        NOTE: This test is skipped because it requires the API server to be restarted
        with the new encryption key after rotation. In the test environment, the
        auth_client fixture creates an app initialized with the OLD_KEY, and there's
        no straightforward way to update its SecretEncryptor mid-test.

        In a real deployment, the sequence is:
        1. Run `rotate-keys` CLI with old and new keys
        2. Update APP_DB_ENCRYPTION_KEY environment variable to new key
        3. Restart API pods (they will use new key on startup)
        4. API can now decrypt the rotated secrets
        """
        # Create credentials
        cred = await _create_test_credential(
            test_db_session,
            bearer_type,
            test_project_id,
            {"token": "pre-rotation-token", "host": "pre.example.com"},
            str(test_user.id),
        )

        # Run rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=50,
            dry_run=False,
        )
        assert exit_code == EXIT_SUCCESS

        # Verify GET works (secrets masked)
        resp = await auth_client.get(f"/api/v1/credentials/{cred.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["inputs"]["token"] == "$encrypted$"  # noqa: S105

        # Verify PATCH works (can update credential)
        resp = await auth_client.patch(
            f"/api/v1/credentials/{cred.id}",
            json={"inputs": {"token": "updated-token", "host": "updated.example.com"}},
        )
        assert resp.status_code == 200

        # Verify new credential can be created
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Post-Rotation Credential",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "new-token", "host": "new.example.com"},
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestMultipleCredentialTypes:
    """Test 8: Rotation with multiple credential types."""

    async def test_rotation_handles_mixed_credential_types(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        basic_auth_type: CredentialType,
        ssh_key_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify rotation works with Bearer, Basic Auth, and SSH key types."""
        # Create 3 bearer tokens
        for i in range(3):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"bearer-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )

        # Create 3 basic auth credentials
        for i in range(3):
            await _create_test_credential(
                test_db_session,
                basic_auth_type,
                test_project_id,
                {"username": f"user{i}", "password": f"pass{i}"},
                str(test_user.id),
            )

        # Create 2 SSH keys
        for i in range(2):
            await _create_test_credential(
                test_db_session,
                ssh_key_type,
                test_project_id,
                {
                    "username": f"sshuser{i}",
                    "ssh_key": f"-----BEGIN RSA PRIVATE KEY-----\nfake-key-{i}\n-----END RSA PRIVATE KEY-----",
                    "passphrase": f"phrase{i}",
                },
                str(test_user.id),
            )

        # Run rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=False,
        )

        assert exit_code == EXIT_SUCCESS

        # Verify all 8 credentials rotated
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        secrets = result.all()
        assert len(secrets) == 8

        # Verify all decrypt with new key
        new_encryptor = SecretEncryptor(NEW_KEY)
        for secret in secrets:
            decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
            assert len(decrypted) > 0  # Has fields


@pytest.mark.asyncio
class TestBatchCommitBehavior:
    """Test 9: Batch commit with failed row handling."""

    async def test_batch_commits_successful_rows_skips_failed(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify successful rows in batch are committed even if one row fails."""
        # Create 15 credentials (batch_size=5 → 3 batches)
        credentials = []
        for i in range(15):
            cred = await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )
            credentials.append(cred)

        # Corrupt credential #8 (will be in batch 2: credentials 5-9)
        wrong_encryptor = SecretEncryptor(WRONG_KEY)
        stmt = select(EncryptedSecret).where(EncryptedSecret.secret_id == credentials[8].secret_id)
        result = await test_db_session.exec(stmt)
        corrupted_secret = result.one()
        corrupted_secret.encrypted_data = wrong_encryptor.encrypt_fields(
            {"token": "bad", "host": "bad.example.com"},
            str(corrupted_secret.secret_id),
        )
        test_db_session.add(corrupted_secret)
        await test_db_session.commit()

        # Run rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=5,
            dry_run=False,
        )

        # Verify partial failure
        assert exit_code == EXIT_PARTIAL_FAILURE

        # Verify batch 1 (0-4) and batch 3 (10-14) fully committed
        # Verify batch 2 (5-9) has 4 successes (skipping #8)
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        all_secrets = result.all()

        new_encryptor = SecretEncryptor(NEW_KEY)
        successful_count = 0

        for secret in all_secrets:
            try:
                new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
                successful_count += 1
            except Exception:
                pass

        # Should have 14 successes (all except corrupted #8)
        assert successful_count == 14


@pytest.mark.asyncio
class TestErrorMessages:
    """Test 10: Error message clarity."""

    async def test_invalid_key_format_error(
        self,
        test_session_factory,
    ) -> None:
        """Verify clear error message for invalid key format."""
        # Run with invalid new key (too short)
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex="short",  # Invalid
            batch_size=50,
            dry_run=False,
        )

        # Verify fatal error
        assert exit_code == EXIT_FATAL

    async def test_identical_keys_error(
        self,
        test_session_factory,
    ) -> None:
        """Verify clear error message when old and new keys are identical."""
        # Run with identical keys
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=OLD_KEY_HEX,  # Same as old
            batch_size=50,
            dry_run=False,
        )

        # Verify fatal error
        assert exit_code == EXIT_FATAL


@pytest.mark.asyncio
class TestIdempotentReRun:
    """Test 11: Re-running rotation is idempotent (already-rotated rows are skipped)."""

    async def test_rerun_after_complete_rotation_returns_success(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Re-running rotation when all rows are already on new key returns exit 0."""
        for i in range(10):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )

        # First rotation
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=50,
            dry_run=False,
        )
        assert exit_code == EXIT_SUCCESS

        # Re-run: all rows already on new key → skipped, exit 0
        exit_code = await rotate_keys(
            old_key_hex=OLD_KEY_HEX,
            new_key_hex=NEW_KEY_HEX,
            batch_size=50,
            dry_run=False,
        )
        assert exit_code == EXIT_SUCCESS

        # Verify all secrets still decrypt with new key
        new_encryptor = SecretEncryptor(NEW_KEY)
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        for secret in result.all():
            decrypted = new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
            assert "token" in decrypted


@pytest.mark.asyncio
class TestInterruptedRotation:
    """Test 6: Interrupted rotation (process killed mid-batch)."""

    async def test_interrupted_rotation_leaves_db_consistent(
        self,
        test_db_session: AsyncSession,
        test_session_factory,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Verify DB is in consistent state if rotation is interrupted mid-batch.

        When rotation is killed mid-batch, uncommitted rows should remain with old key.
        This validates that rotation uses proper transaction boundaries.
        """
        # Create 25 credentials (5 batches with batch_size=5)
        for i in range(25):
            await _create_test_credential(
                test_db_session,
                bearer_type,
                test_project_id,
                {"token": f"token-{i}", "host": f"api{i}.example.com"},
                str(test_user.id),
            )

        # Track commit count and cancel after 2 batches for deterministic interruption
        commit_count = 0
        original_commit: Callable[[], Any] | None = None

        async def commit_wrapper(session) -> None:
            nonlocal commit_count
            assert original_commit is not None
            await original_commit()
            commit_count += 1
            if commit_count == 2:
                msg = "Simulated interruption after 2 batches"
                raise asyncio.CancelledError(msg)

        # Patch session factory to inject cancellation after 2 commits
        def patched_session_factory():  # noqa: ANN202
            nonlocal original_commit
            session = test_session_factory()
            original_commit = session.commit
            session.commit = lambda: commit_wrapper(session)
            return session

        rotate_keys_module._session_factory = patched_session_factory  # type: ignore[assignment]

        try:
            await rotate_keys(
                old_key_hex=OLD_KEY_HEX,
                new_key_hex=NEW_KEY_HEX,
                batch_size=5,
                dry_run=False,
            )
        except asyncio.CancelledError:
            pass  # Expected

        # Verify DB consistency: some secrets rotated, some not
        stmt = select(EncryptedSecret)
        result = await test_db_session.exec(stmt)
        secrets = result.all()

        old_encryptor = SecretEncryptor(OLD_KEY)
        new_encryptor = SecretEncryptor(NEW_KEY)

        old_key_count = 0
        new_key_count = 0

        for secret in secrets:
            # Try decrypting with new key first
            try:
                new_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
                new_key_count += 1
            except EncryptionError:
                # If new key fails, try old key
                try:
                    old_encryptor.decrypt_fields(secret.encrypted_data, str(secret.secret_id))
                    old_key_count += 1
                except EncryptionError:
                    pytest.fail(f"Secret {secret.secret_id} cannot be decrypted with either key")

        # Verify exactly 2 batches (10 credentials) were rotated before cancellation
        assert new_key_count == 10, f"Expected 10 rotated secrets (2 batches), got {new_key_count}"
        assert old_key_count == 15, f"Expected 15 unrotated secrets, got {old_key_count}"
        assert new_key_count + old_key_count == 25, "All secrets should decrypt with one of the keys"
