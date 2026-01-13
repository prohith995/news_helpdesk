"""History storage for analysis reports.

Stores analysis results as JSON files for easy retrieval and browsing.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class HistoryEntry:
    """A saved analysis entry."""
    id: str
    query: str
    workflow: str
    status: str  # completed, abstained, failed
    summary: str
    created_at: str
    execution_time: float
    result: dict  # Full result data


class HistoryStore:
    """Manages storage and retrieval of analysis history."""

    def __init__(self, storage_dir: str | Path | None = None):
        """Initialize history store.

        Args:
            storage_dir: Directory to store history files. Defaults to ~/.newsdesk/history
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".newsdesk" / "history"

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        """Ensure index file exists."""
        if not self.index_file.exists():
            self._write_index([])

    def _read_index(self) -> list[dict]:
        """Read the index file."""
        try:
            with open(self.index_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_index(self, entries: list[dict]):
        """Write the index file."""
        with open(self.index_file, "w") as f:
            json.dump(entries, f, indent=2)

    def save(self, entry: HistoryEntry) -> bool:
        """Save an analysis entry.

        Args:
            entry: The history entry to save

        Returns:
            True if saved successfully
        """
        # Save full entry to individual file
        entry_file = self.storage_dir / f"{entry.id}.json"
        try:
            with open(entry_file, "w") as f:
                json.dump(asdict(entry), f, indent=2)
        except Exception:
            return False

        # Update index with summary info
        index = self._read_index()
        index_entry = {
            "id": entry.id,
            "query": entry.query[:100],  # Truncate for index
            "workflow": entry.workflow,
            "status": entry.status,
            "summary": entry.summary[:200] if entry.summary else "",
            "created_at": entry.created_at,
            "execution_time": entry.execution_time,
        }

        # Add to front of list (most recent first)
        index.insert(0, index_entry)

        # Keep only last 100 entries in index
        index = index[:100]

        self._write_index(index)
        return True

    def list(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List recent history entries.

        Args:
            limit: Max entries to return
            offset: Number of entries to skip

        Returns:
            List of history entry summaries
        """
        index = self._read_index()
        return index[offset:offset + limit]

    def get(self, entry_id: str) -> Optional[HistoryEntry]:
        """Get a specific history entry.

        Args:
            entry_id: The entry ID to retrieve

        Returns:
            The history entry or None if not found
        """
        entry_file = self.storage_dir / f"{entry_id}.json"
        if not entry_file.exists():
            return None

        try:
            with open(entry_file, "r") as f:
                data = json.load(f)
                return HistoryEntry(**data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def delete(self, entry_id: str) -> bool:
        """Delete a history entry.

        Args:
            entry_id: The entry ID to delete

        Returns:
            True if deleted successfully
        """
        entry_file = self.storage_dir / f"{entry_id}.json"

        # Remove from index
        index = self._read_index()
        index = [e for e in index if e["id"] != entry_id]
        self._write_index(index)

        # Remove file
        if entry_file.exists():
            entry_file.unlink()
            return True
        return False

    def clear(self) -> int:
        """Clear all history.

        Returns:
            Number of entries deleted
        """
        index = self._read_index()
        count = len(index)

        # Delete all entry files
        for entry in index:
            entry_file = self.storage_dir / f"{entry['id']}.json"
            if entry_file.exists():
                entry_file.unlink()

        # Clear index
        self._write_index([])
        return count


# Global instance
_store: Optional[HistoryStore] = None


def get_history_store() -> HistoryStore:
    """Get the global history store instance."""
    global _store
    if _store is None:
        _store = HistoryStore()
    return _store
