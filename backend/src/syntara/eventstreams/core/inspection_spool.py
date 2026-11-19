"""Temporary exact-offset storage for replay across repeated Kafka rewinds."""

import sqlite3
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


class InspectionSpool:
    """Store excess replay evidence in a private SQLite temporary database."""

    def __init__(self) -> None:
        """Open a temporary database with a small page cache."""
        self._directory = TemporaryDirectory(prefix="syntara-kafka-inspections-")
        self._connection = sqlite3.connect(Path(self._directory.name) / "evidence.sqlite", isolation_level=None)
        self._connection.execute("PRAGMA cache_size = -64")
        self._connection.execute("CREATE TABLE evidence (offset INTEGER PRIMARY KEY, matched_at TEXT)")
        self.count = 0
        self.first: int | None = None

    def __del__(self) -> None:
        """Release the private temporary database."""
        if hasattr(self, "_connection"):
            self._connection.close()
        if hasattr(self, "_directory"):
            self._directory.cleanup()

    def find(self, offset: int) -> tuple[bool, datetime | None]:
        """Distinguish unknown offsets from known offsets with no saved match."""
        row = self._connection.execute("SELECT matched_at FROM evidence WHERE offset = ?", (offset,)).fetchone()
        if row is None:
            return False, None
        return True, datetime.fromisoformat(row[0]) if row[0] is not None else None

    def remember_match(self, offset: int, received_at: datetime) -> None:
        """Save the first match for an existing offset without adding a row."""
        self._connection.execute(
            "UPDATE evidence SET matched_at = ? WHERE offset = ? AND matched_at IS NULL",
            (received_at.isoformat(), offset),
        )

    def save(self, offsets: set[int], matches: dict[int, datetime]) -> None:
        """Add the in-memory batch atomically while preserving earlier matches."""
        with self._connection:
            self._connection.execute("BEGIN")
            count = (
                self.count
                + self._connection.executemany(
                    "INSERT OR IGNORE INTO evidence VALUES (?, NULL)", ((offset,) for offset in offsets)
                ).rowcount
            )
            count += self._connection.executemany(
                "INSERT OR IGNORE INTO evidence VALUES (?, NULL)", ((offset,) for offset in matches)
            ).rowcount
            self._connection.executemany(
                "UPDATE evidence SET matched_at = ? WHERE offset = ? AND matched_at IS NULL",
                ((stamp.isoformat(), offset) for offset, stamp in matches.items()),
            )
            first = self._read_first()
        self.count = count
        self.first = first

    def resolve(self, offset: int) -> int:
        """Remove one resolved offset and return the remaining count."""
        return self._delete("DELETE FROM evidence WHERE offset = ?", offset)

    def cover_before(self, offset: int) -> int:
        """Remove covered offsets and return the remaining count."""
        return self._delete("DELETE FROM evidence WHERE offset < ?", offset)

    def _delete(self, statement: str, offset: int) -> int:
        with self._connection:
            self._connection.execute("BEGIN")
            deleted = self._connection.execute(statement, (offset,)).rowcount
            first = self._read_first()
        self.count -= deleted
        self.first = first
        return self.count

    def _read_first(self) -> int | None:
        row = self._connection.execute("SELECT offset FROM evidence ORDER BY offset LIMIT 1").fetchone()
        return int(row[0]) if row is not None else None

    def copy(self) -> "InspectionSpool":
        """Give the replacement assignment an independent copy."""
        duplicate = InspectionSpool()
        self._connection.backup(duplicate._connection)
        duplicate.count = self.count
        duplicate.first = self.first
        return duplicate
