import dataclasses
import pytest
from world_runtime.schemas import Effect, Snapshot, Event, ConflictResolution


def test_effect_defaults():
    e = Effect(set={"seal_state": "broken"})
    assert e.set == {"seal_state": "broken"}
    assert e.unset == []
    assert e.intent == ""
    assert e.priority == 1


def test_effect_priority():
    e = Effect(set={"x": 1}, priority=4)
    assert e.priority == 4


def test_snapshot_defaults():
    s = Snapshot()
    assert s.tick == 0
    assert s.seal_state == "intact"
    assert s.han_zheng_status == "alive"
    assert s.lu_status == "threatened"
    assert s.dynamic == {}
    assert s.unresolved_conflicts == []


def test_snapshot_dynamic():
    s = Snapshot()
    s.dynamic["new_rule"] = "立约修正案"
    assert s.dynamic["new_rule"] == "立约修正案"


def test_event_fields():
    e = Event(event_id="e1", tick=0, event_type="action",
              agent_id="韩峥", agent_type="character", layer="L1",
              payload={"nl_action": "保护陆"})
    assert e.event_id == "e1"
    assert e.tick == 0
    assert e.payload["nl_action"] == "保护陆"


def test_conflict_resolution_unresolved():
    c = ConflictResolution(key="seal_state", conflicting=[],
                            winner=None, reason="same_priority_unresolved",
                            unresolved=True)
    assert c.unresolved is True
    assert c.winner is None


def test_effect_unset_only_constructs():
    # set 有默认值，可只传 unset
    e = Effect(unset=["temp"])
    assert e.set == {}
    assert e.unset == ["temp"]
    assert e.priority == 1


def test_effect_is_frozen():
    e = Effect(set={"x": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.priority = 4


def test_event_is_frozen():
    ev = Event(event_id="e1", tick=0, event_type="action")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.tick = 1
