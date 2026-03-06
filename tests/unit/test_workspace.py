"""Tests for GlobalWorkspace."""

from gwt_context.domain.models import ActivationState, MemoryItem, MemoryType
from gwt_context.domain.workspace import GlobalWorkspace


def _make_item(id: str = "test1", content: str = "test content") -> MemoryItem:
    return MemoryItem(id=id, content=content, memory_type=MemoryType.SEMANTIC)


class TestGlobalWorkspace:
    def test_initial_state(self):
        ws = GlobalWorkspace(capacity=3)
        assert ws.capacity == 3
        assert ws.occupied_count == 0
        assert ws.free_count == 3
        assert ws.items == []

    def test_admit_success(self):
        ws = GlobalWorkspace(capacity=2)
        item = _make_item()
        assert ws.admit(item) is True
        assert ws.occupied_count == 1
        assert item.activation_state == ActivationState.CONSCIOUS
        assert item.entered_workspace_at is not None

    def test_admit_full(self):
        ws = GlobalWorkspace(capacity=1)
        ws.admit(_make_item("a"))
        assert ws.admit(_make_item("b")) is False
        assert ws.occupied_count == 1

    def test_evict(self):
        ws = GlobalWorkspace(capacity=2)
        item = _make_item("x")
        ws.admit(item)
        evicted = ws.evict("x")
        assert evicted is not None
        assert evicted.id == "x"
        assert evicted.activation_state == ActivationState.PRECONSCIOUS
        assert ws.occupied_count == 0

    def test_evict_nonexistent(self):
        ws = GlobalWorkspace(capacity=2)
        assert ws.evict("nope") is None

    def test_contains(self):
        ws = GlobalWorkspace(capacity=3)
        item = _make_item("abc")
        ws.admit(item)
        assert ws.contains("abc") is True
        assert ws.contains("xyz") is False

    def test_clear(self):
        ws = GlobalWorkspace(capacity=3)
        ws.admit(_make_item("a"))
        ws.admit(_make_item("b"))
        evicted = ws.clear()
        assert len(evicted) == 2
        assert ws.occupied_count == 0

    def test_broadcast_text_empty(self):
        ws = GlobalWorkspace(capacity=3)
        text = ws.get_broadcast_text()
        assert "empty" in text.lower()

    def test_broadcast_text_with_items(self):
        ws = GlobalWorkspace(capacity=3)
        item = _make_item("id1", "important fact")
        item.activation_level = 0.85
        ws.admit(item)
        text = ws.get_broadcast_text()
        assert "important fact" in text
        assert "0.85" in text
        assert "1/3" in text

    def test_item_ids(self):
        ws = GlobalWorkspace(capacity=3)
        ws.admit(_make_item("a"))
        ws.admit(_make_item("b"))
        assert ws.item_ids == {"a", "b"}
