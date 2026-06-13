"""
MVP1 端到端：用现有中场景 .output 反向验证 NL→effect→snapshot 链。

步骤：
1. 读 .output 的 hetero_traces（130 条 NL action）
2. 按 tick 分组
3. 每 tick：extractor 提取 effect[] → reducer fold → snapshot 落盘
4. 输出 10 个 snapshot + 确定性 replay 验证

Q3 鸿沟信号：观察多少 effect 的 set 为空（"未落地"）——比例越高，
说明从"决策陈述"到"实际状态变化"的鸿沟越大。
"""
import json
from pathlib import Path
from dataclasses import asdict

from .schemas import Snapshot, Event
from .event_store import EventStore
from .reducer import reducer
from .extractor import extract_effects_for_tick
from .llm import call_llm


HERE = Path(__file__).parent
DEFAULT_OUTPUT = r"C:\Users\Administrator\AppData\Local\Temp\claude\D--novel-test\9692d31b-6302-4415-8f13-99df06a36bd0\tasks\wcngxa9px.output"


def load_hetero_actions(output_path: str) -> dict:
    """读 .output，按 tick 分组返回 NL action。"""
    data = json.loads(Path(output_path).read_text(encoding="utf-8"))
    result = data.get("result", data)
    traces = result.get("hetero_traces", [])
    by_tick = {}
    for t in traces:
        by_tick.setdefault(t["tick"], []).append({
            "agent_id": t.get("collective_name") or t.get("agent_id"),
            "agent_type": t.get("agent_type", "character"),
            "layer": t.get("layer", "L1"),
            "nl_action": t.get("action", ""),
        })
    return dict(sorted(by_tick.items()))


def run_mvp1(output_path: str, model: str = "haiku"):
    outdir = HERE
    store = EventStore(outdir / "events.jsonl")
    if (outdir / "events.jsonl").exists():
        (outdir / "events.jsonl").unlink()
    snapdir = outdir / "snapshots"
    snapdir.mkdir(exist_ok=True)

    actions_by_tick = load_hetero_actions(output_path)
    print(f"加载 {sum(len(v) for v in actions_by_tick.values())} 条 action，"
          f"{len(actions_by_tick)} 个 tick")

    snapshot = Snapshot(tick=-1)
    all_effects_log = []

    # Q3 鸿沟统计
    total_effects = 0
    empty_set_effects = 0

    for tick in sorted(actions_by_tick.keys()):
        actions = actions_by_tick[tick]
        print(f"\n=== tick {tick} ({len(actions)} actions) ===")

        try:
            effects = extract_effects_for_tick(actions, snapshot, tick,
                                               call_fn=call_llm, model=model,
                                               event_store=store)
        except Exception as ex:
            print(f"  [WARN] extractor 失败，跳过该 tick：{ex}")
            effects = []

        for eff in effects:
            total_effects += 1
            is_empty = len(eff.set) == 0
            if is_empty:
                empty_set_effects += 1
            tag = " (set空·未落地)" if is_empty else ""
            print(f"  effect: set={eff.set} priority={eff.priority}"
                  f" intent={eff.intent[:40]}{tag}")

        for i, eff in enumerate(effects):
            store.append(Event(
                event_id=f"eff_t{tick}_{i}", tick=tick, event_type="effect",
                payload={"effect": asdict(eff)}))
        all_effects_log.append((tick, effects))

        snapshot, resolutions = reducer(effects, snapshot)
        if resolutions:
            print(f"  {len(resolutions)} 条冲突裁决：")
            for r in resolutions:
                tag = "未裁决" if r.unresolved else f"winner priority={r.winner[0].priority}"
                print(f"    {r.key}: {tag}")

        snap_path = snapdir / f"snap_t{snapshot.tick}.json"
        snap_path.write_text(
            json.dumps(asdict(snapshot), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  snapshot -> {snap_path.name}: seal={snapshot.seal_state}, "
              f"han_zheng={snapshot.han_zheng_status}, "
              f"alliance={snapshot.alliance_resolution[:30]}")

    print("\n=== 确定性 replay 验证 ===")
    snap2 = Snapshot(tick=-1)
    for tick, effects in all_effects_log:
        snap2, _ = reducer(effects, snap2)
    replay_match = json.dumps(asdict(snap2), ensure_ascii=False) == \
                   json.dumps(asdict(snapshot), ensure_ascii=False)
    print(f"replay 一致性: {'PASS' if replay_match else 'FAIL'}")

    print("\n=== Q3 鸿沟统计 ===")
    if total_effects:
        empty_ratio = empty_set_effects / total_effects
        print(f"总 effect 数: {total_effects}")
        print(f"set 为空（未落地）effect 数: {empty_set_effects}")
        print(f"未落地比例: {empty_ratio:.1%}")
        print(f"已落地比例: {1 - empty_ratio:.1%}")

    return snapshot, replay_match, (total_effects, empty_set_effects)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_OUTPUT)
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()
    snapshot, ok, (tot, empty) = run_mvp1(args.input, args.model)
    print(f"\n最终 snapshot tick={snapshot.tick}, replay ok={ok}")
