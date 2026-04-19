"""SQLite persistence for memory items, goals, and broadcast records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from gwt_context.domain.models import (
    ActivationState,
    BroadcastRecord,
    Goal,
    MemoryItem,
    MemoryType,
)


class SQLiteMemoryStore:
    """Persists GWT domain objects to SQLite.

    Schema: memory_items, goals, broadcasts tables.
    Embeddings stored as JSON arrays (not binary — simplicity over perf).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                summary TEXT DEFAULT '',
                memory_type TEXT NOT NULL,
                activation_state TEXT NOT NULL,
                source TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                relevance_score REAL DEFAULT 0,
                recency_score REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                activation_level REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                entered_workspace_at TEXT,
                embedding TEXT,
                linked_ids TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                keywords TEXT DEFAULT '[]',
                priority REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                embedding TEXT
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                workspace_snapshot TEXT DEFAULT '[]',
                goal_id TEXT,
                formatted_content TEXT DEFAULT '',
                evicted_ids TEXT DEFAULT '[]',
                admitted_ids TEXT DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_items_state
                ON memory_items(activation_state);
            CREATE INDEX IF NOT EXISTS idx_items_type
                ON memory_items(memory_type);
            CREATE INDEX IF NOT EXISTS idx_goals_active
                ON goals(active);
        """)
        self._conn.commit()

    # --- MemoryItem CRUD ---

    def save_item(self, item: MemoryItem) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO memory_items
            (id, content, summary, memory_type, activation_state, source, tags,
             relevance_score, recency_score, access_count, activation_level,
             created_at, last_accessed, entered_workspace_at, embedding, linked_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.content,
                item.summary,
                item.memory_type.value,
                item.activation_state.value,
                item.source,
                json.dumps(item.tags),
                item.relevance_score,
                item.recency_score,
                item.access_count,
                item.activation_level,
                item.created_at.isoformat(),
                item.last_accessed.isoformat(),
                item.entered_workspace_at.isoformat() if item.entered_workspace_at else None,
                json.dumps(item.embedding) if item.embedding else None,
                json.dumps(item.linked_ids),
            ),
        )
        self._conn.commit()

    def get_item(self, item_id: str) -> MemoryItem | None:
        row = self._conn.execute(
            "SELECT * FROM memory_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def get_items_by_state(self, state: ActivationState) -> list[MemoryItem]:
        rows = self._conn.execute(
            "SELECT * FROM memory_items WHERE activation_state = ?",
            (state.value,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_all_items(self) -> list[MemoryItem]:
        rows = self._conn.execute("SELECT * FROM memory_items").fetchall()
        return [self._row_to_item(r) for r in rows]

    def update_state(self, item_id: str, state: ActivationState) -> None:
        self._conn.execute(
            "UPDATE memory_items SET activation_state = ? WHERE id = ?",
            (state.value, item_id),
        )
        self._conn.commit()

    def update_item(self, item: MemoryItem) -> None:
        """Update all fields of an existing item."""
        self.save_item(item)

    def delete_item(self, item_id: str) -> None:
        self._conn.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
        self._conn.commit()

    def count_items(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()
        return int(row[0]) if row else 0

    def add_link(self, source_id: str, target_id: str) -> None:
        """Add bidirectional link between two items."""
        for a, b in [(source_id, target_id), (target_id, source_id)]:
            item = self.get_item(a)
            if item and b not in item.linked_ids:
                item.linked_ids.append(b)
                self.save_item(item)

    # --- Goal CRUD ---

    def save_goal(self, goal: Goal) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO goals
            (id, description, keywords, priority, created_at, active, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                goal.id,
                goal.description,
                json.dumps(goal.keywords),
                goal.priority,
                goal.created_at.isoformat(),
                1 if goal.active else 0,
                json.dumps(goal.embedding) if goal.embedding else None,
            ),
        )
        self._conn.commit()

    def get_active_goals(self) -> list[Goal]:
        rows = self._conn.execute(
            "SELECT * FROM goals WHERE active = 1"
        ).fetchall()
        return [self._row_to_goal(r) for r in rows]

    def deactivate_all_goals(self) -> None:
        self._conn.execute("UPDATE goals SET active = 0")
        self._conn.commit()

    def deactivate_all(self) -> None:
        """Deactivate all active goals.

        Compatibility shim for MemoryRepositoryPort.
        """
        self.deactivate_all_goals()

    # --- Broadcast CRUD ---

    def save_broadcast(self, record: BroadcastRecord) -> None:
        self._conn.execute(
            """INSERT INTO broadcasts
            (id, timestamp, workspace_snapshot, goal_id,
             formatted_content, evicted_ids, admitted_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.timestamp.isoformat(),
                json.dumps(record.workspace_snapshot),
                record.goal_id,
                record.formatted_content,
                json.dumps(record.evicted_ids),
                json.dumps(record.admitted_ids),
            ),
        )
        self._conn.commit()

    def get_broadcast_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM broadcasts").fetchone()
        return int(row[0]) if row else 0

    # --- Conversion helpers ---

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            content=row["content"],
            summary=row["summary"],
            memory_type=MemoryType(row["memory_type"]),
            activation_state=ActivationState(row["activation_state"]),
            source=row["source"],
            tags=json.loads(row["tags"]),
            relevance_score=row["relevance_score"],
            recency_score=row["recency_score"],
            access_count=row["access_count"],
            activation_level=row["activation_level"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            entered_workspace_at=(
                datetime.fromisoformat(row["entered_workspace_at"])
                if row["entered_workspace_at"]
                else None
            ),
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            linked_ids=json.loads(row["linked_ids"]),
        )

    @staticmethod
    def _row_to_goal(row: sqlite3.Row) -> Goal:
        return Goal(
            id=row["id"],
            description=row["description"],
            keywords=json.loads(row["keywords"]),
            priority=row["priority"],
            created_at=datetime.fromisoformat(row["created_at"]),
            active=bool(row["active"]),
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        )

    def close(self) -> None:
        self._conn.close()
