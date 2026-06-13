from world_runtime.extractor import extract_effects_for_tick
from world_runtime.reducer import reducer
from world_runtime.schemas import Snapshot, Effect


def _mock_call_fn_factory(response: dict):
    """返回一个假的 call_fn，忽略 prompt 直接返回固定 structured_output（dict）。"""
    def _fn(prompt, **kwargs):
        return response
    return _fn


def test_integration_grounded_folds_to_snapshot():
    mock = _mock_call_fn_factory({"effects": [
        {"agent_id": "world_will", "set": {"seal_state": "weakening"},
         "unset": [], "intent": "征兆", "grounded": True},
    ]})
    actions = [{"agent_id": "world_will", "agent_type": "world_will",
                "layer": "L3", "nl_action": "释放征兆"}]
    effects = extract_effects_for_tick(actions, Snapshot(), 0, call_fn=mock)
    assert len(effects) == 1
    assert effects[0].grounded is True
    snap, _ = reducer(effects, Snapshot())
    assert snap.seal_state == "weakening"
    assert snap.tick == 1


def test_integration_ungrounded_preserved_not_folded():
    mock = _mock_call_fn_factory({"effects": [
        {"agent_id": "旁观者", "set": {"seal_state": "broken"},
         "unset": [], "intent": "观察记录", "grounded": False},
    ]})
    actions = [{"agent_id": "旁观者", "agent_type": "character",
                "layer": "L1", "nl_action": "观察记录"}]
    effects = extract_effects_for_tick(actions, Snapshot(), 0, call_fn=mock)
    assert effects[0].grounded is False
    snap, _ = reducer(effects, Snapshot())
    assert snap.seal_state == "intact"  # 未落地不 fold
    assert len(effects) == 1  # 但 effect 仍存在（意图层保留）


def test_integration_mixed_priority_and_grounded():
    mock = _mock_call_fn_factory({"effects": [
        {"agent_id": "world_will", "set": {"seal_state": "broken"},
         "unset": [], "intent": "裁决", "grounded": True},
        {"agent_id": "小队", "set": {"seal_state": "protected"},
         "unset": [], "intent": "保护", "grounded": True},
        {"agent_id": "旁观者", "set": {"seal_state": "observed"},
         "unset": [], "intent": "观察", "grounded": False},
    ]})
    actions = [
        {"agent_id": "world_will", "agent_type": "world_will", "layer": "L3", "nl_action": "裁决"},
        {"agent_id": "小队", "agent_type": "collective", "layer": "L2", "nl_action": "保护"},
        {"agent_id": "旁观者", "agent_type": "character", "layer": "L1", "nl_action": "观察"},
    ]
    effects = extract_effects_for_tick(actions, Snapshot(), 0, call_fn=mock)
    snap, resolutions = reducer(effects, Snapshot())
    # 只 2 个 grounded 冲突 seal_state，world_will(4) 胜小队(2)
    assert snap.seal_state == "broken"
    assert len(resolutions) == 1
    assert resolutions[0].unresolved is False