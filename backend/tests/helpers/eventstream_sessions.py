"""Isolated async-session lifecycle ports shared by event worker unit tests."""

from unittest.mock import MagicMock

from sqlmodel.ext.asyncio.session import AsyncSession


def session_factory() -> tuple[MagicMock, list[MagicMock]]:
    """Track fresh sessions and transaction exits without executing SQL."""
    sessions: list[MagicMock] = []

    def create() -> MagicMock:
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = False
        session.begin.return_value.__aexit__.return_value = False
        sessions.append(session)
        return session

    return MagicMock(side_effect=create), sessions
