# 世界渲染 Runtime MVP1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 reducer + event store + effect extractor，用现有中场景 .output（130 条 NL action）反向验证"NL→effect→snapshot"链成立，决定 reducer 范式是否立住。

**Architecture:** 纯 Python runtime。reducer 是纯函数（fold effects → snapshot，可确定性单测）；effect extractor 通过 claude.cmd subprocess 把 NL action 翻译成结构化 effect；event store 是 append-only JSONL（单一真相源）。MVP1 用离线 extract + reduce 跑现有数据，零运行时 agent LLM。

**Tech Stack:** Python 3（dataclasses / json / subprocess / pathlib / pytest）、claude.cmd CLI（`-p --bare --output-format json`）、JSONL 文件存储。

**关联 spec:** `docs/superpowers/specs/2026-06-13-world-rendering-runtime-design.md` §9 MVP1。

**关键决策（plan 细化）:**
- Snapshot 字段用**英文键名**（`han_zheng_status` 而非中文），避免 LLM 产 effect 时键名不一致。spec §3.3 的中文字段是示意。
- Snapshot 预定义 7 个关键状态（seal_state / han_zheng_status / lu_status / squad_resolution / network_resolution / alliance_resolution / alien_stance）+ dynamic dict 容纳涌现。
- priority：world_will=4 > law_enforcer=3 > collective=2 > character=1。

---

## File Structure

| 文件 | 职责 | 测试 |
|------|------|------|
| `world_runtime/__init__.py` | 包标记 | — |
| `world_runtime/schemas.py` | Event/Effect/Snapshot/ConflictResolution dataclass | test_schemas.py |
| `world_runtime/event_store.py` | append-only JSONL + load + query | test_event_store.py |
| `world_runtime/reducer.py` | 纯函数 fold + 优先级裁决 + 同优先级未裁决 | test_reducer.py |
| `world_runtime/llm.py` | call_llm wrapper（subprocess + telemetry） | （手动验证）|
| `world_runtime/extractor.py` | NL action → effect[]（LLM） | （手动验证，LLM 难单测）|
| `world_runtime/run_mvp1.py` | 端到端：extract .output → reduce → snapshots | （端到端跑）|

包路径：`docs/research/world_runtime/`（与 render_poc 同级）。测试在 `docs/research/world_runtime/tests/`。

---

## Task 1: 项目脚手架 + schemas.py

**Files:**
- Create: `docs/research/world_runtime/__init__.py`
- Create: `docs/research/world_runtime/schemas.py`
- Create: `docs/research/world_runtime/tests/__init__.py`
- Create: `docs/research/world_runtime/tests/test_schemas.py`

- [ ] **Step 1: 建目录 + 空包标记**

```bash
mkdir -p docs/research/world_runtime/tests
```

写 `docs/research/world_runtime/__init__.py`（空文件）和 `docs/research/world_runtime/tests/__init__.py`（空文件）。

- [ ] **Step 2: 写失败测试 `tests/test_schemas.py`**

```python
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
```

- [ ] **Step 3: 运行测试验证失败**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_schemas.py -v
```
Expected: FAIL（`ModuleNotFoundError: No module named 'world_runtime.schemas'`）

- [ ] **Step 4: 实现 `schemas.py`**

```python
from dataclasses import dataclass, field
from typing import Literal, Any


@dataclass(frozen=True)
class Effect:
    """结构化状态增量（delta 风格，Fowler 教训）。"""
    set: dict
    unset: list = field(default_factory=list)
    intent: str = ""
    priority: int = 1  # world_will=4 > law_enforcer=3 > collective=2 > character=1


@dataclass
class Snapshot:
    """世界状态（混合：预定义强类型 + dynamic 涌现）。"""
    tick: int = 0
    # 预定义关键状态
    seal_state: str = "intact"            # intact | weakening | broken
    han_zheng_status: str = "alive"       # 韩峥
    lu_status: str = "threatened"         # 陆
    squad_resolution: str = ""            # 小队决议
    network_resolution: str = ""          # 网络决议
    alliance_resolution: str = ""         # 联盟决议
    alien_stance: str = ""                # 异族立场
    # 动态涌现
    dynamic: dict = field(default_factory=dict)
    # 未裁决矛盾（Wolf：同优先级冲突保留为燃料）
    unresolved_conflicts: list = field(default_factory=list)


@dataclass(frozen=True)
class Event:
    """event log 单元（append-only）。"""
    event_id: str
    tick: int
    event_type: Literal[
        "action", "effect", "state_delta", "conflict_resolution",
        "call", "memory_write",
    ]
    agent_id: str | None = None
    agent_type: str | None = None
    layer: str | None = None
    payload: dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class ConflictResolution:
    """reducer 冲突裁决记录。"""
    key: str
    conflicting: list          # [(effect, value), ...]
    winner: tuple | None       # (effect, value) 或 None（未裁决）
    reason: str
    unresolved: bool
```

- [ ] **Step 5: 运行测试验证通过**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_schemas.py -v
```
Expected: PASS（6 passed）

- [ ] **Step 6: Commit**

```bash
git add docs/research/world_runtime/
git commit -m "feat(world-runtime): schemas - Event/Effect/Snapshot/ConflictResolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: event_store.py（append + load + query）

**Files:**
- Create: `docs/research/world_runtime/event_store.py`
- Create: `docs/research/world_runtime/tests/test_event_store.py`

- [ ] **Step 1: 写失败测试 `tests/test_event_store.py`**

```python
import json
from pathlib import Path
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_event_store.py -v
```
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `event_store.py`**

```python
import json
from pathlib import Path
from dataclasses import asdict
from .schemas import Event


class EventStore:
    """append-only JSONL event log（单一真相源）。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def query(self, tick=None, agent_id=None, event_type=None) -> list[dict]:
        events = self.load_all()
        result = []
        for e in events:
            if tick is not None and e.get("tick") != tick:
                continue
            if agent_id is not None and e.get("agent_id") != agent_id:
                continue
            if event_type is not None and e.get("event_type") != event_type:
                continue
            result.append(e)
        return result
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_event_store.py -v
```
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add docs/research/world_runtime/event_store.py docs/research/world_runtime/tests/test_event_store.py
git commit -m "feat(world-runtime): event_store - append-only JSONL + query

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: reducer.py 基础 fold（单 effect，无冲突）

**Files:**
- Create: `docs/research/world_runtime/reducer.py`
- Create: `docs/research/world_runtime/tests/test_reducer.py`

- [ ] **Step 1: 写失败测试 `tests/test_reducer.py`（基础 fold）**

```python
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
    assert s0.seal_state == "weakening"  # 原 snapshot 不被修改
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py -v
```
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `reducer.py`（基础版，无冲突处理）**

```python
from copy import deepcopy
from .schemas import Effect, Snapshot, ConflictResolution

# 预定义状态字段（强类型），其余进 dynamic
PREDEFINED_FIELDS = {
    "seal_state", "han_zheng_status", "lu_status",
    "squad_resolution", "network_resolution", "alliance_resolution",
    "alien_stance",
}


def apply_key(snap: Snapshot, key: str, value):
    """把一个 effect 的 set 应用到 snapshot（预定义字段 setattr，其余进 dynamic）。"""
    if key in PREDEFINED_FIELDS:
        setattr(snap, key, value)
    else:
        snap.dynamic[key] = value


def reducer(effects: list[Effect], S_t: Snapshot) -> tuple[Snapshot, list[ConflictResolution]]:
    """纯函数 fold：effects + S_t → (S_{t+1}, conflict_resolutions)。"""
    new_state = deepcopy(S_t)
    resolutions = []

    # group effects by affected key（只看 set）
    by_key = {}
    for eff in effects:
        for k, v in eff.set.items():
            by_key.setdefault(k, []).append((eff, v))

    for key, candidates in by_key.items():
        if len(candidates) == 1:
            apply_key(new_state, key, candidates[0][1])
        else:
            # 冲突处理（Task 4/5 实现，这里先占位用最高 priority）
            ranked = sorted(candidates, key=lambda c: -c[0].priority)
            apply_key(new_state, key, ranked[0][1])

    # 应用 unset
    for eff in effects:
        for k in eff.unset:
            if k in new_state.dynamic:
                del new_state.dynamic[k]

    new_state.tick = S_t.tick + 1
    return new_state, resolutions
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py -v
```
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add docs/research/world_runtime/reducer.py docs/research/world_runtime/tests/test_reducer.py
git commit -m "feat(world-runtime): reducer basic fold (single effect, no conflict)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: reducer priority 冲突裁决

**Files:**
- Modify: `docs/research/world_runtime/reducer.py`
- Modify: `docs/research/world_runtime/tests/test_reducer.py`（追加测试）

- [ ] **Step 1: 追加失败测试（priority 裁决）**

追加到 `tests/test_reducer.py` 末尾：

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py::test_conflict_higher_priority_wins -v
```
Expected: FAIL（resolutions 为空，因为 Task 3 还没记 resolution）

- [ ] **Step 3: 修改 `reducer.py` 的冲突分支**

把 reducer 函数里的冲突分支替换为：

```python
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
                # 同优先级：未裁决（Task 5 处理，暂记 unresolved）
                resolutions.append(ConflictResolution(
                    key=key, conflicting=candidates,
                    winner=None, reason="same_priority_unresolved",
                    unresolved=True))
                apply_key(new_state, key, ranked[0][1])  # 暂用第一条
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py -v
```
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add docs/research/world_runtime/reducer.py docs/research/world_runtime/tests/test_reducer.py
git commit -m "feat(world-runtime): reducer priority-based conflict resolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: reducer 同优先级未裁决（矛盾保留）

**Files:**
- Modify: `docs/research/world_runtime/reducer.py`
- Modify: `docs/research/world_runtime/tests/test_reducer.py`

- [ ] **Step 1: 追加失败测试（同优先级未裁决 + 记入 snapshot）**

追加到 `tests/test_reducer.py` 末尾：

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py::test_same_priority_unresolved_recorded -v
```
Expected: FAIL（unresolved_conflicts 还是空）

- [ ] **Step 3: 修改 reducer——未裁决矛盾记入 snapshot**

在 reducer 函数里，同优先级分支改为：

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd docs/research/world_runtime && python -m pytest tests/test_reducer.py -v
```
Expected: PASS（9 passed）

- [ ] **Step 5: 跑全部测试确认无回归**

```bash
cd docs/research/world_runtime && python -m pytest tests/ -v
```
Expected: PASS（schemas 6 + event_store 5 + reducer 9 = 20 passed）

- [ ] **Step 6: Commit**

```bash
git add docs/research/world_runtime/reducer.py docs/research/world_runtime/tests/test_reducer.py
git commit -m "feat(world-runtime): reducer records same-priority conflicts as fuel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: llm.py call_llm wrapper

**Files:**
- Create: `docs/research/world_runtime/llm.py`

注：subprocess 调用难单测（依赖 claude.cmd），用手动验证。Telemetry 在 Task 7 端到端时验证。

- [ ] **Step 1: 实现 `llm.py`**

```python
import subprocess
import json
import time
import sys

# Windows GBK 控制台兼容
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def call_llm(prompt: str, model: str = "sonnet",
             agent_id: str = None, tick: int = None,
             event_store=None) -> str:
    """通过 claude.cmd subprocess 调 LLM。所有调用统一入口（telemetry 可选）。

    --bare: 跳过项目 CLAUDE.md/hooks（纯 LLM，避免污染）
    --output-format json: 取结构化 result + usage
    """
    t0 = time.time()
    try:
        r = subprocess.run(
            ["claude", "-p", "--bare", "--output-format", "json", "--model", model],
            input=prompt, capture_output=True, text=True, encoding="utf-8",
        )
        duration_ms = (time.time() - t0) * 1000
        parsed = json.loads(r.stdout)
        output = parsed.get("result", "")
        usage = parsed.get("usage", {})

        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_{int(duration_ms)}",
                tick=tick if tick is not None else 0,
                event_type="call",
                agent_id=agent_id,
                payload={
                    "prompt": prompt, "output": output,
                    "duration_ms": duration_ms, "tokens": usage,
                    "model": model, "status": "ok",
                },
            ))
        return output
    except Exception as e:
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_err",
                tick=tick if tick is not None else 0,
                event_type="call", agent_id=agent_id,
                payload={"status": "error", "error": str(e), "model": model},
            ))
        raise
```

- [ ] **Step 2: 手动验证（确认 claude.cmd 调通 + JSON 解析）**

```bash
cd docs/research/world_runtime && python -c "
from llm import call_llm
out = call_llm('回复一个字：好')
print(repr(out))
"
```
Expected: 打印包含"好"的字符串（确认 claude.cmd 调通、JSON 解析成功）。若报错，检查 claude.cmd 是否在 PATH、`--output-format json` 是否返回含 `result` 字段。

- [ ] **Step 3: Commit**

```bash
git add docs/research/world_runtime/llm.py
git commit -m "feat(world-runtime): llm call_llm wrapper (claude.cmd subprocess + telemetry)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: extractor.py（NL action → effect[]）

**Files:**
- Create: `docs/research/world_runtime/extractor.py`

- [ ] **Step 1: 实现 `extractor.py`**

```python
import json
from .schemas import Effect
from .llm import call_llm

# agent_type → priority 映射
PRIORITY_MAP = {
    "world_will": 4,
    "law_enforcer": 3,
    "collective": 2,
    "character": 1,
}

EXTRACTOR_PROMPT = """你是 effect 提取器。把本 tick 各 agent 的自然语言 action 翻译成结构化 effect，用于 reducer fold 世界状态。

当前世界状态 snapshot：
{snapshot_json}

世界规则（3 个必然性）：
1. 封印注定在"自愿生命牺牲"条件下破
2. 封印破后释放远古力量，触发文明选择
3. 文明选择不可被代理

本 tick 的 actions（agent_id / agent_type / layer / nl_action）：
{actions_json}

可用的预定义状态变量（优先用这些 key）：
- seal_state: intact | weakening | broken
- han_zheng_status: alive | sacrificed | restrained | decided
- lu_status: threatened | safe | dead
- squad_resolution / network_resolution / alliance_resolution: 自由文本（集体决议）
- alien_stance: 自由文本
新的状态变量可放入 set（会进 dynamic）。

请为每个 agent 产出一个 effect。规则：
- set: 该 agent 本 tick 对世界状态造成的**实际变化**（不是意图）。若 action 只是陈述/观望无实际状态变化，set 为空 {{}}。
- unset: 清除的状态变量。
- intent: 意图摘要（中文，给渲染层用，不参与 fold）。
- priority 由 agent_type 决定，不要自己改。

输出**纯 JSON**（不要 markdown 代码块）：
{{"effects": [
  {{"agent_id": "...", "set": {{...}}, "unset": [...], "intent": "..."}}
]}}

注意：从"决策陈述"提取"实际状态变化"可能有鸿沟——若 action 是纯意图未落地，set 留空并在 intent 注明"未落地"。"""


def extract_effects_for_tick(actions: list[dict], snapshot, tick: int,
                              call_fn=call_llm, model: str = "sonnet") -> list[Effect]:
    """对一个 tick 的所有 NL action 提取 effect[]。

    actions: [{agent_id, agent_type, layer, nl_action}, ...]
    返回: [Effect, ...]
    """
    from dataclasses import asdict
    snap_json = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
    actions_json = json.dumps(actions, ensure_ascii=False, indent=2)
    prompt = EXTRACTOR_PROMPT.format(snapshot_json=snap_json, actions_json=actions_json)

    raw = call_fn(prompt, model=model, agent_id="_extractor", tick=tick)

    # 清理可能的 markdown 代码块包裹
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    parsed = json.loads(raw)
    effects = []
    for e in parsed.get("effects", []):
        agent_type = next(
            (a["agent_type"] for a in actions if a.get("agent_id") == e.get("agent_id")),
            "character",
        )
        effects.append(Effect(
            set=e.get("set", {}),
            unset=e.get("unset", []),
            intent=e.get("intent", ""),
            priority=PRIORITY_MAP.get(agent_type, 1),
        ))
    return effects
```

- [ ] **Step 2: 手动验证（小样本，确认能产出可 fold 的 effect）**

```bash
cd docs/research/world_runtime && python -c "
from extractor import extract_effects_for_tick
from schemas import Snapshot
actions = [{'agent_id':'world_will','agent_type':'world_will','layer':'L3','nl_action':'释放封印将破的征兆'}]
effs = extract_effects_for_tick(actions, Snapshot(), 0)
for e in effs:
    print(e)
"
```
Expected: 打印 1 个 Effect（priority=4，set 含状态变化或空）。若 LLM 输出非 JSON，检查 prompt 引导 + markdown 清理逻辑。

- [ ] **Step 3: Commit**

```bash
git add docs/research/world_runtime/extractor.py
git commit -m "feat(world-runtime): extractor NL action -> structured effect

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: run_mvp1.py 端到端（extract .output → reduce → snapshots）

**Files:**
- Create: `docs/research/world_runtime/run_mvp1.py`

- [ ] **Step 1: 实现 `run_mvp1.py`**

```python
"""
MVP1 端到端：用现有中场景 .output 反向验证 NL→effect→snapshot 链。

步骤：
1. 读 .output 的 hetero_traces（130 条 NL action）
2. 按 tick 分组
3. 每 tick：extractor 提取 effect[] → reducer fold → snapshot 落盘
4. 输出 10 个 snapshot + 确定性 replay 验证
"""
import json
import argparse
from pathlib import Path
from dataclasses import asdict

from .schemas import Snapshot, Event
from .event_store import EventStore
from .reducer import reducer
from .extractor import extract_effects_for_tick
from .llm import call_llm


HERE = Path(__file__).parent
DEFAULT_OUTPUT = r"C:\Users\Administrator\AppData\Local\Temp\claude\D--novel-test\9692d31b-6302-4415-8f13-99df06a36bd0\tasks\wcngxa9px.output"


def load_hetero_actions(output_path: str) -> dict[int, list[dict]]:
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


def run_mvp1(output_path: str, model: str = "sonnet"):
    outdir = HERE
    store = EventStore(outdir / "events.jsonl")
    # 清空旧 log
    if (outdir / "events.jsonl").exists():
        (outdir / "events.jsonl").unlink()
    snapdir = outdir / "snapshots"
    snapdir.mkdir(exist_ok=True)

    actions_by_tick = load_hetero_actions(output_path)
    print(f"加载 {sum(len(v) for v in actions_by_tick.values())} 条 action，"
          f"{len(actions_by_tick)} 个 tick")

    snapshot = Snapshot(tick=-1)  # tick 0 之前是空状态
    all_effects_log = []

    for tick in sorted(actions_by_tick.keys()):
        actions = actions_by_tick[tick]
        print(f"\n=== tick {tick} ({len(actions)} actions) ===")

        # extract
        effects = extract_effects_for_tick(actions, snapshot, tick,
                                           call_fn=call_llm, model=model)
        for eff in effects:
            print(f"  effect: set={eff.set} priority={eff.priority}")

        # 记 event
        for i, eff in enumerate(effects):
            store.append(Event(
                event_id=f"eff_t{tick}_{i}", tick=tick, event_type="effect",
                payload={"effect": asdict(eff)}))
        all_effects_log.append((tick, effects))

        # reduce
        snapshot, resolutions = reducer(effects, snapshot)
        if resolutions:
            print(f"  {len(resolutions)} 条冲突裁决：")
            for r in resolutions:
                tag = "未裁决" if r.unresolved else f"winner priority={r.winner[0].priority}"
                print(f"    {r.key}: {tag}")

        # 落盘 snapshot
        snap_path = snapdir / f"snap_t{snapshot.tick}.json"
        snap_path.write_text(
            json.dumps(asdict(snapshot), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  snapshot → {snap_path.name}: seal={snapshot.seal_state}, "
              f"韩峥={snapshot.han_zheng_status}, 联盟={snapshot.alliance_resolution[:30]}")

    print("\n=== 确定性 replay 验证 ===")
    # Q1: 同 effect log 重 fold，snapshot 必须一致
    snap2 = Snapshot(tick=-1)
    for tick, effects in all_effects_log:
        snap2, _ = reducer(effects, snap2)
    replay_match = json.dumps(asdict(snap2), ensure_ascii=False) == \
                   json.dumps(asdict(snapshot), ensure_ascii=False)
    print(f"replay 一致性: {'PASS ✅' if replay_match else 'FAIL ❌'}")

    return snapshot, replay_match


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE.parent))  # 让 from world_runtime import 生效
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_OUTPUT)
    ap.add_argument("--model", default="sonnet")
    args = ap.parse_args()
    # 直接调用（包内运行）
    snapshot, ok = run_mvp1(args.input, args.model)
    print(f"\n最终 snapshot tick={snapshot.tick}")
    print(f"replay ok={ok}")
```

- [ ] **Step 2: 端到端运行（会调 ~10 次 LLM extractor）**

```bash
cd D:/novel_test/docs/research && python -m world_runtime.run_mvp1 --model sonnet
```
Expected: 逐 tick 打印 effect / 冲突裁决 / snapshot，最后打印 replay 一致性 PASS。10 个 snapshot 文件落到 `world_runtime/snapshots/`。

若 `.output` 路径不存在（临时文件可能被清理），改用已存的 `docs/research/render_poc/event_log.json`（含同样 trace）——调整 `load_hetero_actions` 读 JSON 的 hetero_events 字段。

- [ ] **Step 3: Commit**

```bash
git add docs/research/world_runtime/run_mvp1.py docs/research/world_runtime/snapshots/ docs/research/world_runtime/events.jsonl
git commit -m "feat(world-runtime): MVP1 end-to-end - extract .output -> reduce -> snapshots

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 反向验证 + MVP1 报告（带目的回答 Q1/Q2/Q3）

**Files:**
- Create: `docs/research/world_runtime/MVP1_REPORT.md`

- [ ] **Step 1: 检查 snapshot 序列合理性（人工核 Q2）**

```bash
cd D:/novel_test/docs/research/world_runtime && python -c "
import json
from pathlib import Path
for p in sorted(Path('snapshots').glob('snap_t*.json')):
    s = json.loads(p.read_text(encoding='utf-8'))
    print(f\"{p.stem}: seal={s['seal_state']}, 韩峥={s['han_zheng_status']}, \"
          f\"联盟={s['alliance_resolution'][:40]}, 冲突={len(s['unresolved_conflicts'])}\")
"
```
对照中场景已知结局核验：封印最终是否 `broken`？韩峥 status 是否合理？联盟/网络/小队决议是否演化？

- [ ] **Step 2: 写 `MVP1_REPORT.md`（带目的回答 3 个问题）**

```markdown
# MVP1 报告 — reducer 机制 + effect schema 反向验证

## 带的问题 + 回答

### Q1：纯函数 reducer 能否确定性产出 snapshot？（机制）
- [ ] replay 一致性：PASS / FAIL
- 证据：run_mvp1 输出的 replay 一致性行

### Q2：effect schema 能否表达中场景关键状态？（表达力）
- [ ] 7 个预定义字段是否被 effect 覆盖：seal_state / han_zheng_status / lu_status / 3 个集体决议 / alien_stance
- [ ] dynamic 是否有涌现（新 key）
- 证据：snapshots/snap_t*.json 的字段分布

### Q3：extractor 从 pilot 决策陈述型 action 提取可靠性（数据局限）
- [ ] 多少 action 的 set 为空（"未落地"）？比例？
- [ ] 提取出的 effect 是否荒谬（人工抽检 5 条）
- [ ] 结论：鸿沟多大 → 是否需要 MVP2b（为 fold 设计的新数据）

## 判定
- 若 Q1 PASS + Q2 覆盖：reducer 范式立住，进入 MVP2
- 若 fold 出荒谬状态：记录具体哪里（schema/effect/extractor），反馈设计

## 局限（诚实）
- pilot action 是决策陈述非状态变化，Q3 可靠性受限
- 单次 extract（LLM 随机性未控制）
- snapshot 正确性无 ground truth，靠人工核中场景已知结局
```

填完报告的每个 `[ ]`（基于 Task 8 运行结果）。

- [ ] **Step 3: Commit**

```bash
git add docs/research/world_runtime/MVP1_REPORT.md
git commit -m "docs(world-runtime): MVP1 report - Q1/Q2/Q3 verdict

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage（MVP1 §9）**：
- schemas（Event/Effect/Snapshot）→ Task 1 ✓
- event store（append/query）→ Task 2 ✓
- reducer（fold + priority + 同优先级）→ Task 3/4/5 ✓
- effect extractor（NL→effect）→ Task 7 ✓
- call_llm wrapper → Task 6 ✓
- 反向验证（fold 10 snapshot + Q1/Q2/Q3）→ Task 8/9 ✓
- reducer 纯函数单测 → Task 3/4/5 ✓
- recall/memory_store/runtime/dashboard → **不在 MVP1**（spec §9 明确留 MVP3/4）✓

**Placeholder scan**：无 TBD/TODO，所有代码步骤含完整代码。✓

**Type consistency**：
- `Effect.set/unset/intent/priority` 跨 Task 1/3/4/5/7 一致 ✓
- `Snapshot` 字段（seal_state 等）跨 schemas/reducer/test 一致 ✓
- `reducer(effects, S_t) -> (Snapshot, [ConflictResolution])` 签名跨 Task 3/4/5/8 一致 ✓
- `extract_effects_for_tick(actions, snapshot, tick, call_fn, model)` 签名跨 Task 7/8 一致 ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-13-world-runtime-mvp1.md`. 两个执行选项见下。
