"""Integration tests for SQLite storage and vector index."""

import tempfile
from pathlib import Path

import pytest

from gwt_context.domain.models import ActivationState, Goal, MemoryItem, MemoryType
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def store(tmp_dir):
    s = SQLiteMemoryStore(db_path=tmp_dir / "test.db")
    yield s
    s.close()


@pytest.fixture
def vi(tmp_dir):
    return VectorIndex(dim=3, path=tmp_dir / "vectors.bin")


class TestSQLiteMemoryStore:
    def test_save_and_get_item(self, store):
        item = MemoryItem(
            id="abc",
            content="hello world",
            memory_type=MemoryType.SEMANTIC,
            tags=["test", "greeting"],
            embedding=[0.1, 0.2, 0.3],
        )
        store.save_item(item)
        loaded = store.get_item("abc")
        assert loaded is not None
        assert loaded.content == "hello world"
        assert loaded.tags == ["test", "greeting"]
        assert loaded.embedding == [0.1, 0.2, 0.3]
        assert loaded.memory_type == MemoryType.SEMANTIC

    def test_get_nonexistent(self, store):
        assert store.get_item("nope") is None

    def test_update_state(self, store):
        item = MemoryItem(id="x", content="data")
        store.save_item(item)
        store.update_state("x", ActivationState.CONSCIOUS)
        loaded = store.get_item("x")
        assert loaded.activation_state == ActivationState.CONSCIOUS

    def test_get_items_by_state(self, store):
        for i, state in enumerate([ActivationState.LONG_TERM, ActivationState.PRECONSCIOUS, ActivationState.LONG_TERM]):
            store.save_item(MemoryItem(id=f"item{i}", content=f"c{i}", activation_state=state))
        lt = store.get_items_by_state(ActivationState.LONG_TERM)
        assert len(lt) == 2
        pc = store.get_items_by_state(ActivationState.PRECONSCIOUS)
        assert len(pc) == 1

    def test_delete_item(self, store):
        store.save_item(MemoryItem(id="del", content="bye"))
        store.delete_item("del")
        assert store.get_item("del") is None

    def test_count_items(self, store):
        assert store.count_items() == 0
        store.save_item(MemoryItem(id="a", content="1"))
        store.save_item(MemoryItem(id="b", content="2"))
        assert store.count_items() == 2

    def test_add_link(self, store):
        store.save_item(MemoryItem(id="s", content="source"))
        store.save_item(MemoryItem(id="t", content="target"))
        store.add_link("s", "t")
        s = store.get_item("s")
        t = store.get_item("t")
        assert "t" in s.linked_ids
        assert "s" in t.linked_ids

    def test_goals(self, store):
        g = Goal(id="g1", description="find answer", priority=1.5, embedding=[0.1, 0.2])
        store.save_goal(g)
        active = store.get_active_goals()
        assert len(active) == 1
        assert active[0].description == "find answer"
        assert active[0].priority == 1.5

        store.deactivate_all_goals()
        assert len(store.get_active_goals()) == 0

    def test_broadcast_count(self, store):
        from gwt_context.domain.models import BroadcastRecord
        assert store.get_broadcast_count() == 0
        store.save_broadcast(BroadcastRecord(formatted_content="test"))
        assert store.get_broadcast_count() == 1


class TestVectorIndex:
    def test_add_and_query(self, vi):
        vi.add("a", [1.0, 0.0, 0.0])
        vi.add("b", [0.0, 1.0, 0.0])
        vi.add("c", [0.0, 0.0, 1.0])

        results = vi.query([1.0, 0.0, 0.0], k=2)
        assert len(results) == 2
        assert results[0][0] == "a"  # Most similar
        assert results[0][1] > 0.99

    def test_empty_query(self, vi):
        assert vi.query([1, 0, 0]) == []

    def test_remove(self, vi):
        vi.add("x", [1.0, 0.0, 0.0])
        vi.remove("x")
        assert vi.count == 0

    def test_update(self, vi):
        vi.add("x", [1.0, 0.0, 0.0])
        vi.add("x", [0.0, 1.0, 0.0])  # Update
        assert vi.count == 1
        results = vi.query([0.0, 1.0, 0.0], k=1)
        assert results[0][0] == "x"
        assert results[0][1] > 0.99

    def test_save_and_load(self, tmp_dir):
        path = tmp_dir / "idx.bin"
        vi1 = VectorIndex(dim=3, path=path)
        vi1.add("a", [1.0, 0.0, 0.0])
        vi1.add("b", [0.0, 1.0, 0.0])
        vi1.save()

        vi2 = VectorIndex(dim=3, path=path)
        assert vi2.count == 2
        results = vi2.query([1.0, 0.0, 0.0], k=1)
        assert results[0][0] == "a"
