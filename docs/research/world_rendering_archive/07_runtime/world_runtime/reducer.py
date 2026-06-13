from copy import deepcopy
from .schemas import Effect, Snapshot, ConflictResolution, PREDEFINED_FIELDS


def apply_key(snap: Snapshot, key: str, value):
    """把一个 effect 的 set 应用到 snapshot（预定义字段 setattr，其余进 dynamic）。"""
    if key in PREDEFINED_FIELDS:
        setattr(snap, key, value)
    else:
        snap.dynamic[key] = value


def reducer(effects: list[Effect], S_t: Snapshot) -> tuple[Snapshot, list]:
    """纯函数 fold：effects + S_t → (S_{t+1}, conflict_resolutions)。

    - 按 key 分组 effect
    - 单 effect 直接 apply
    - 多 effect 冲突：按 priority 裁决（world_will=4 > law_enforcer=3 > collective=2 > character=1）
    - 同优先级冲突：未裁决，记入 snapshot.unresolved_conflicts（Wolf：矛盾即燃料）
    - deepcopy 不改原 S_t，tick 自增 1
    """
    new_state = deepcopy(S_t)
    resolutions = []

    # 只 fold grounded=true（grounded=false 是意图层，保留 event 不 fold）
    grounded_effects = [e for e in effects if getattr(e, "grounded", True)]

    # group effects by affected key（只看 set）
    by_key = {}
    for eff in grounded_effects:
        for k, v in eff.set.items():
            by_key.setdefault(k, []).append((eff, v))

    for key, candidates in by_key.items():
        if len(candidates) == 1:
            apply_key(new_state, key, candidates[0][1])
        else:
            # 冲突：按 priority 降序
            ranked = sorted(candidates, key=lambda c: -c[0].priority)
            if ranked[0][0].priority > ranked[1][0].priority:
                # 优先级不同：高者胜
                apply_key(new_state, key, ranked[0][1])
                resolutions.append(ConflictResolution(
                    key=key, conflicting=candidates,
                    winner=ranked[0], reason="priority", unresolved=False))
            else:
                # 同优先级：未裁决，记入 snapshot.unresolved_conflicts（Wolf：矛盾即燃料）
                conflict_record = {
                    "key": key,
                    "candidates": [{"value": c[1], "priority": c[0].priority,
                                    "intent": c[0].intent} for c in candidates],
                }
                new_state.unresolved_conflicts.append(conflict_record)
                resolutions.append(ConflictResolution(
                    key=key, conflicting=candidates,
                    winner=None, reason="same_priority_unresolved",
                    unresolved=True))
                apply_key(new_state, key, ranked[0][1])  # 暂用第一条

    # 应用 unset（仅 dynamic）
    for eff in grounded_effects:
        for k in eff.unset:
            if k in new_state.dynamic:
                del new_state.dynamic[k]

    new_state.tick = S_t.tick + 1
    return new_state, resolutions