from world_runtime.reducer import reducer, apply_key
from world_runtime.schemas import Effect, Snapshot


def test_single_effect_applies_to_predefined():
    s0 = Snapshot()
    eff = Effect(set={"seal_state": "broken"}, priority=4)
    s1, resolutions = reducer([eff], s0)
    assert s1.seal_state == "broken"
    assert s1.tick == 1
    assert resolutions == []


def test_single_effect_applies_to_dynamic():
    s0 = Snapshot()
    eff = Effect(set={"new_faction_stance": "hostile"}, priority=2)
    s1, _ = reducer([eff], s0)
    assert s1.dynamic["new_faction_stance"] == "hostile"


def test_unset_removes_dynamic():
    s0 = Snapshot()
    s0.dynamic["temp"] = "x"
    eff = Effect(set={}, unset=["temp"])
    s1, _ = reducer([eff], s0)
    assert "temp" not in s1.dynamic


def test_tick_increments():
    s0 = Snapshot(tick=5)
    s1, _ = reducer([], s0)
    assert s1.tick == 6


def test_no_effects_returns_copy():
    s0 = Snapshot()
    s0.seal_state = "weakening"
    s1, _ = reducer([], s0)
    assert s1.seal_state == "weakening"
    assert s0.seal_state == "weakening"  # 原 snapshot 不被修改（deepcopy）


def test_conflict_higher_priority_wins():
    s0 = Snapshot()
    eff_will = Effect(set={"seal_state": "broken"}, priority=4)       # world_will
    eff_char = Effect(set={"seal_state": "protected"}, priority=1)    # character
    s1, resolutions = reducer([eff_will, eff_char], s0)
    assert s1.seal_state == "broken"  # 高 priority 胜
    assert len(resolutions) == 1
    assert resolutions[0].key == "seal_state"
    assert resolutions[0].unresolved is False
    assert resolutions[0].winner[0] is eff_will
    assert resolutions[0].reason == "priority"


def test_conflict_law_enforcer_beats_collective():
    s0 = Snapshot()
    eff_law = Effect(set={"han_zheng_status": "restrained"}, priority=3)
    eff_coll = Effect(set={"han_zheng_status": "free"}, priority=2)
    s1, resolutions = reducer([eff_law, eff_coll], s0)
    assert s1.han_zheng_status == "restrained"
    assert len(resolutions) == 1