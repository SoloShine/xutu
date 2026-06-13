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