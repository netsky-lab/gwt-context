"""Tests for BroadcastAssembler."""

from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.models import Goal, MemoryItem, MemoryType
from gwt_context.domain.workspace import GlobalWorkspace


def _item(id: str, content: str) -> MemoryItem:
    return MemoryItem(id=id, content=content, memory_type=MemoryType.SEMANTIC)


class TestBroadcastAssembler:
    def test_empty_workspace(self):
        ba = BroadcastAssembler()
        ws = GlobalWorkspace(capacity=3)
        record = ba.assemble(ws, [])
        assert "0/3" in record.formatted_content
        assert record.workspace_snapshot == []

    def test_with_items(self):
        ba = BroadcastAssembler()
        ws = GlobalWorkspace(capacity=3)
        item = _item("id1", "the earth is round")
        item.activation_level = 0.9
        ws.admit(item)

        record = ba.assemble(ws, [])
        assert "the earth is round" in record.formatted_content
        assert "1/3" in record.formatted_content
        assert "id1" in record.workspace_snapshot

    def test_with_goals(self):
        ba = BroadcastAssembler()
        ws = GlobalWorkspace(capacity=3)
        goal = Goal(description="find the answer")
        record = ba.assemble(ws, [goal])
        assert "find the answer" in record.formatted_content

    def test_transition_info(self):
        ba = BroadcastAssembler()
        ws = GlobalWorkspace(capacity=3)
        admitted = _item("new1", "new info")
        evicted = _item("old1", "old info")

        record = ba.assemble(ws, [], evicted=[evicted], admitted=[admitted])
        assert "ADMITTED" in record.formatted_content
        assert "EVICTED" in record.formatted_content
        assert "new1" in record.admitted_ids
        assert "old1" in record.evicted_ids
