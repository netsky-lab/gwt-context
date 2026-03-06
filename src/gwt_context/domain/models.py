"""Core domain models for GWT context management.

All models are pure data — no I/O, no side effects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MemoryType(Enum):
    """Classification of memory content."""

    EPISODIC = "episodic"       # Events, conversations, observations
    SEMANTIC = "semantic"       # Facts, knowledge, definitions
    PROCEDURAL = "procedural"   # How-to, instructions, patterns
    WORKING = "working"         # Intermediate reasoning results


class ActivationState(Enum):
    """Where a memory item currently resides in the GWT hierarchy."""

    LONG_TERM = "long_term"           # Persistent storage only
    PRECONSCIOUS = "preconscious"     # In ranked buffer, candidate for workspace
    CONSCIOUS = "conscious"           # In workspace, actively broadcast


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class MemoryItem:
    """Atomic unit of memory in the GWT system.

    Flows through: long_term → preconscious (buffer) → conscious (workspace).
    Specialists score items; winners compete for workspace slots.
    """

    id: str = field(default_factory=_short_id)
    content: str = ""
    summary: str = ""
    memory_type: MemoryType = MemoryType.SEMANTIC
    activation_state: ActivationState = ActivationState.LONG_TERM
    source: str = ""
    tags: list[str] = field(default_factory=list)

    # Scoring — updated by specialists during competition
    relevance_score: float = 0.0
    recency_score: float = 0.0
    access_count: int = 0
    activation_level: float = 0.0  # Combined score after competition

    # Timestamps
    created_at: datetime = field(default_factory=_now)
    last_accessed: datetime = field(default_factory=_now)
    entered_workspace_at: Optional[datetime] = None

    # Dense vector embedding (None until computed)
    embedding: Optional[list[float]] = None

    # Bidirectional links to other items — enables multi-hop reasoning
    linked_ids: list[str] = field(default_factory=list)

    def token_estimate(self) -> int:
        """Rough token count (~4 chars per token)."""
        return len(self.content) // 4

    def touch(self) -> None:
        """Update access metadata."""
        self.last_accessed = _now()
        self.access_count += 1


@dataclass
class Goal:
    """Task objective that modulates competition (GWT marker #6).

    Active goals bias the competition — items semantically closer
    to the goal get a multiplicative boost.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    embedding: Optional[list[float]] = None
    priority: float = 1.0
    created_at: datetime = field(default_factory=_now)
    active: bool = True


@dataclass
class WorkspaceSlot:
    """A single slot in the capacity-limited global workspace."""

    index: int
    item: Optional[MemoryItem] = None
    entered_at: Optional[datetime] = None
    broadcast_count: int = 0

    @property
    def is_empty(self) -> bool:
        return self.item is None


@dataclass
class CompetitionResult:
    """Output of one competition round."""

    winners: list[MemoryItem]
    evicted: list[MemoryItem]
    scores: dict[str, float]  # item_id → final activation score
    reason: str = ""


@dataclass
class BroadcastRecord:
    """Record of a single broadcast event for audit/replay."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: datetime = field(default_factory=_now)
    workspace_snapshot: list[str] = field(default_factory=list)  # item IDs
    goal_id: Optional[str] = None
    formatted_content: str = ""
    evicted_ids: list[str] = field(default_factory=list)
    admitted_ids: list[str] = field(default_factory=list)
