from world_runtime.event_store import EventStore
from world_runtime.schemas import Event


def test_append_and_load(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    store.append(Event(event_id="e1", tick=0, event_type="action",
                       agent_id="韩峥", payload={"nl_action": "保护陆"}))
    store.append(Event(event_id="e2", tick=0, event_type="effect",
                       agent_id="韩峥", payload={"effect": {}}))
    events = store.load_all()
    assert len(events) == 2
    assert events[0]["event_id"] == "e1"
    assert events[1]["event_type"] == "effect"


def test_load_empty_when_no_file(tmp_path):
    store = EventStore(tmp_path / "nonexistent.jsonl")
    assert store.load_all() == []


def test_query_by_tick(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    store.append(Event(event_id="e1", tick=0, event_type="action"))
    store.append(Event(event_id="e2", tick=1, event_type="action"))
    store.append(Event(event_id="e3", tick=1, event_type="effect"))
    t1 = store.query(tick=1)
    assert len(t1) == 2
    assert all(e["tick"] == 1 for e in t1)


def test_query_by_agent_and_type(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    store.append(Event(event_id="e1", tick=0, event_type="action", agent_id="韩峥"))
    store.append(Event(event_id="e2", tick=0, event_type="action", agent_id="陆"))
    store.append(Event(event_id="e3", tick=0, event_type="effect", agent_id="韩峥"))
    result = store.query(agent_id="韩峥", event_type="effect")
    assert len(result) == 1
    assert result[0]["event_id"] == "e3"


def test_append_preserves_unicode(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    store.append(Event(event_id="e1", tick=0, event_type="action",
                       agent_id="韩峥", payload={"nl_action": "破封救陆"}))
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert "韩峥" in raw
    assert "破封救陆" in raw