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


def test_same_priority_unresolved_recorded():
    s0 = Snapshot()
    eff1 = Effect(set={"squad_resolution": "protect"}, priority=2)
    eff2 = Effect(set={"squad_resolution": "abandon"}, priority=2)
    s1, resolutions = reducer([eff1, eff2], s0)
    assert len(resolutions) == 1
    assert resolutions[0].unresolved is True
    assert resolutions[0].winner is None
    # 未裁决矛盾记入 snapshot.unresolved_conflicts
    assert len(s1.unresolved_conflicts) == 1
    assert s1.unresolved_conflicts[0]["key"] == "squad_resolution"


def test_multiple_keys_independent():
    s0 = Snapshot()
    # seal_state 冲突（不同优先级，裁决）
    eff_a = Effect(set={"seal_state": "broken"}, priority=4)
    eff_b = Effect(set={"seal_state": "intact"}, priority=1)
    # han_zheng_status 无冲突
    eff_c = Effect(set={"han_zheng_status": "decided"}, priority=2)
    s1, resolutions = reducer([eff_a, eff_b, eff_c], s0)
    assert s1.seal_state == "broken"
    assert s1.han_zheng_status == "decided"
    assert len(resolutions) == 1  # 只有 seal_state 冲突


def test_three_candidates_mixed_priority():
    # 3+ effect 同 key，混合优先级，最高胜
    s0 = Snapshot()
    eff_a = Effect(set={"seal_state": "broken"}, priority=4)
    eff_b = Effect(set={"seal_state": "intact"}, priority=1)
    eff_c = Effect(set={"seal_state": "weakening"}, priority=1)
    s1, resolutions = reducer([eff_a, eff_b, eff_c], s0)
    assert s1.seal_state == "broken"
    assert len(resolutions) == 1
    assert resolutions[0].unresolved is False


def test_unset_predefined_is_noop():
    # unset 预定义字段不改变它（unset 只作用于 dynamic）
    s0 = Snapshot()
    s0.seal_state = "weakening"
    eff = Effect(set={}, unset=["seal_state"])
    s1, _ = reducer([eff], s0)
    assert s1.seal_state == "weakening"  # 预定义字段 unset 无效


def test_unset_only_effect_works():
    # 纯 unset effect（set 默认 {}）能删 dynamic
    s0 = Snapshot()
    s0.dynamic["temp"] = "x"
    eff = Effect(unset=["temp"])  # 不传 set
    s1, _ = reducer([eff], s0)
    assert "temp" not in s1.dynamic