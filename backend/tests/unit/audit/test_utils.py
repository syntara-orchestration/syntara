"""Unit tests for audit utilities."""

import itertools
from uuid import UUID, uuid4

import pytest

from syntara.audit.models.audit_event import EventSeverity
from syntara.audit.utils import escalate_actor_type, escalate_severity, resolve_actor_type, sanitize_actor_username
from syntara.core.constants import FieldLimits
from syntara.core.models.principal import PrincipalType, service_principal_id


class TestEscalateSeverity:
    """Direct unit tests for ``escalate_severity``.

    These tests lock in the ``>=`` boundary semantics of the helper
    independently of the context managers and decorators that call it,
    so a regression in the ordering table cannot be masked by higher-level
    tests that only exercise a subset of the matrix.
    """

    @pytest.mark.parametrize(
        ("current", "minimum", "expected"),
        [
            # current == INFO: always escalated to minimum
            (EventSeverity.INFO, EventSeverity.INFO, EventSeverity.INFO),
            (EventSeverity.INFO, EventSeverity.WARNING, EventSeverity.WARNING),
            (EventSeverity.INFO, EventSeverity.ERROR, EventSeverity.ERROR),
            (EventSeverity.INFO, EventSeverity.CRITICAL, EventSeverity.CRITICAL),
            # current == WARNING: preserved when >= minimum
            (EventSeverity.WARNING, EventSeverity.INFO, EventSeverity.WARNING),
            (EventSeverity.WARNING, EventSeverity.WARNING, EventSeverity.WARNING),
            (EventSeverity.WARNING, EventSeverity.ERROR, EventSeverity.ERROR),
            (EventSeverity.WARNING, EventSeverity.CRITICAL, EventSeverity.CRITICAL),
            # current == ERROR: preserved when >= minimum
            (EventSeverity.ERROR, EventSeverity.INFO, EventSeverity.ERROR),
            (EventSeverity.ERROR, EventSeverity.WARNING, EventSeverity.ERROR),
            (EventSeverity.ERROR, EventSeverity.ERROR, EventSeverity.ERROR),
            (EventSeverity.ERROR, EventSeverity.CRITICAL, EventSeverity.CRITICAL),
            # current == CRITICAL: never downgraded — this is the core
            # correctness property the helper exists to guarantee.
            (EventSeverity.CRITICAL, EventSeverity.INFO, EventSeverity.CRITICAL),
            (EventSeverity.CRITICAL, EventSeverity.WARNING, EventSeverity.CRITICAL),
            (EventSeverity.CRITICAL, EventSeverity.ERROR, EventSeverity.CRITICAL),
            (EventSeverity.CRITICAL, EventSeverity.CRITICAL, EventSeverity.CRITICAL),
        ],
    )
    def test_escalate_severity_matrix(
        self,
        current: EventSeverity,
        minimum: EventSeverity,
        expected: EventSeverity,
    ) -> None:
        """Every (current, minimum) pair returns the more severe of the two."""
        assert escalate_severity(current, minimum) == expected

    def test_escalate_severity_covers_every_enum_member(self) -> None:
        """Exhaustiveness guard: the ranking table must cover every member.

        If a new ``EventSeverity`` member is ever added without updating the
        internal ordering, ``escalate_severity`` would raise ``KeyError`` at
        runtime. Iterating the full cartesian product catches that regression
        at test time instead.
        """
        for current, minimum in itertools.product(EventSeverity, EventSeverity):
            # Must not raise, and must return one of the two inputs.
            result = escalate_severity(current, minimum)
            assert result in {current, minimum}


class TestEscalateActorType:
    """Unit tests for ``escalate_actor_type``.

    Validates that known service principal IDs are classified as
    PrincipalType.SERVICE while all other user IDs are PrincipalType.USER.
    """

    @pytest.mark.parametrize(
        ("actor_id", "expected"),
        [
            # Service principal → SERVICE
            (service_principal_id("backend.ao.svc"), PrincipalType.SERVICE),
            # Regular users → USER
            (uuid4(), PrincipalType.USER),
            (UUID("00000000-0000-0000-0000-000000000000"), PrincipalType.USER),
        ],
    )
    def test_escalate_actor_type(
        self,
        actor_id: UUID,
        expected: PrincipalType,
    ) -> None:
        """Service principal returns SERVICE, all others return USER."""
        assert escalate_actor_type(actor_id) == expected


class TestResolveActorType:
    """Unit tests for ``resolve_actor_type``.

    Validates the resolution order: explicit principal_type override >
    system user escalation > USER default.
    """

    def test_explicit_principal_type_wins(self) -> None:
        """An explicit principal_type is returned without checking actor_id."""
        assert (
            resolve_actor_type(
                actor_id=uuid4(),
                principal_type=PrincipalType.SERVICE_ACCOUNT,
            )
            == PrincipalType.SERVICE_ACCOUNT
        )

    def test_service_principal_escalated(self) -> None:
        """Service principal actor_id escalates to SERVICE when no override is set."""
        assert (
            resolve_actor_type(
                actor_id=service_principal_id("backend.ao.svc"),
            )
            == PrincipalType.SERVICE
        )

    def test_regular_user_defaults(self) -> None:
        """Non-system actor_id with no override returns USER."""
        assert resolve_actor_type(actor_id=uuid4()) == PrincipalType.USER

    def test_no_args_returns_user(self) -> None:
        """No actor_id and no override returns USER."""
        assert resolve_actor_type() == PrincipalType.USER

    def test_none_principal_type_falls_through(self) -> None:
        """Explicit None principal_type does not short-circuit."""
        assert (
            resolve_actor_type(
                actor_id=service_principal_id("backend.ao.svc"),
                principal_type=None,
            )
            == PrincipalType.SERVICE
        )


class TestSanitizeActorUsername:
    """Unit tests for ``sanitize_actor_username``."""

    def test_none_returns_none(self) -> None:
        assert sanitize_actor_username(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert sanitize_actor_username("") is None

    def test_normal_username_unchanged(self) -> None:
        assert sanitize_actor_username("admin") == "admin"

    def test_strips_control_characters(self) -> None:
        assert sanitize_actor_username("user\r\n.name") == "user.name"

    def test_truncates_to_max_length(self) -> None:
        long_name = "a" * 500
        result = sanitize_actor_username(long_name)
        assert result is not None
        assert len(result) == FieldLimits.NAME_MAX_LENGTH

    def test_exactly_max_length_unchanged(self) -> None:
        name = "b" * FieldLimits.NAME_MAX_LENGTH
        assert sanitize_actor_username(name) == name

    def test_control_chars_only_returns_none(self) -> None:
        assert sanitize_actor_username("\r\n\t") is None

    def test_idempotent(self) -> None:
        result = sanitize_actor_username("admin")
        assert sanitize_actor_username(result) == result
