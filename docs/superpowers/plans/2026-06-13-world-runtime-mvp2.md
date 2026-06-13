# 世界渲染 Runtime MVP2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 用 `--json-schema` 消除 extractor 跨运行波动 + Effect 加 `grounded` 显式分层意图/事件层 + reducer 只 fold grounded。

**Architecture:** 增量改 MVP1 代码。call_llm 加 `response_schema`（→ `--json-schema` constrained decoding）；Effect 加 `grounded`/`agent_id`/`agent_type`；extractor 用 schema 强制结构化输出；reducer 只 fold `grounded=true`。无 schema 时保持 MVP1 行为（向后兼容）。

**Tech Stack:** Python 3、claude.cmd `--json-schema`（已验证存在+工作）、pytest。

**关联 spec:** `docs/superpowers/specs/2026-06-13-world-runtime-mvp2-design.md`

---

## File Structure

| 文件 | 改动 |
|------|------|
| `world_runtime/schemas.py` | Effect 加 grounded/agent_id/agent_type |
| `world_runtime/llm.py` | call_llm 加 response_schema（--json-schema + structured_output）|
| `world_runtime/extractor.py` | 定义 EFFECT_JSON_SCHEMA，用 response_schema |
| `world_runtime/reducer.py` | 只 fold grounded=true |
| `world_runtime/tests/test_schemas.py` | +grounded/agent_id 测试 |
| `world_runtime/tests/test_reducer.py` | +grounded=false 不 fold 测试 |
| `world_runtime/tests/test_integration.py` | 新：mocked extract→reduce→snapshot |
| `world_runtime/run_mvp1.py` | （验证用，不改逻辑）|

包路径：`docs/research/world_runtime/`。测试 `python -m pytest world_runtime/tests/ -v` 从 `docs/research/` 跑。

---

## Task 1: Effect schema 加 grounded + agent_id/agent_type

**Files:**
- Modify: `docs/research/world_runtime/schemas.py`（Effect dataclass）
- Modify: `docs/research/world_runtime/tests/test_schemas.py`

- [ ] **Step 1: 追加失败测试**（test_schemas.py 末尾）

```python
def test_effect_grounded_default():
    e = Effect(set={"x": 1})
    assert e.grounded is True
    assert e.agent_id == ""
    assert e.agent_type == "character"


def test_effect_grounded_false():
    e = Effect(set={}, intent="观望", grounded=False, agent_id="旁观者")
    assert e.grounded is False
    assert e.agent_id == "旁观者"
```

- [ ] **Step 2: 运行验证失败**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/test_schemas.py::test_effect_grounded_default -v
```
Expected: FAIL（Effect 无 grounded 字段）

- [ ] **Step 3: 改 schemas.py 的 Effect**——加 3 字段（agent_id/agent_type 在前，有默认值，向后兼容）

```python
@dataclass(frozen=True)
class Effect:
    """结构化状态增量（delta 风格，Fowler 教训）。"""
    agent_id: str = ""
    agent_type: str = "character"
    set: dict[str, Any] = field(default_factory=dict)
    unset: list[str] = field(default_factory=list)
    intent: str = ""
    grounded: bool = True       # True=事件层(fold) / False=意图层(保留不fold)
    priority: int = 1
```

- [ ] **Step 4: 运行全部测试验证通过 + 无回归**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/ -v
```
Expected: PASS（26 原有 + 2 新 = 28）

- [ ] **Step 5: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/schemas.py docs/research/world_runtime/tests/test_schemas.py
git commit -m "feat(world-runtime): Effect add grounded/agent_id/agent_type

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: call_llm 加 response_schema（--json-schema）

**Files:**
- Modify: `docs/research/world_runtime/llm.py`

- [ ] **Step 1: 改 call_llm**——加 `response_schema` 参数。schema 给定时传 `--json-schema`，返回 `structured_output`（dict）；不给时保持 MVP1（返回 result str）。

修改 call_llm 签名 + cmd 构造 + output 取值：
```python
def call_llm(prompt: str, model: str = "sonnet",
             agent_id: str = None, tick: int = None,
             event_store=None, response_schema: dict = None):
    """通过 claude.cmd subprocess 调 LLM。

    response_schema 给定时：用 --json-schema constrained decoding，返回 structured_output（dict）。
    不给时：返回 result（str），保持 MVP1 行为。
    """
    import shutil
    claude_cmd = shutil.which("claude") or "claude"
    t0 = time.time()
    try:
        cmd = [claude_cmd, "-p", "--bare", "--output-format", "json", "--model", model]
        if response_schema is not None:
            cmd += ["--json-schema", json.dumps(response_schema, ensure_ascii=False)]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8")
        duration_ms = (time.time() - t0) * 1000
        parsed = json.loads(r.stdout)
        if response_schema is not None:
            output = parsed.get("structured_output", {})
        else:
            output = parsed.get("result", "")
        usage = parsed.get("usage", {})
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_{int(duration_ms)}",
                tick=tick if tick is not None else 0, event_type="call", agent_id=agent_id,
                payload={"prompt": prompt, "output": output, "duration_ms": duration_ms,
                         "tokens": usage, "model": model, "status": "ok",
                         "schema": bool(response_schema)}))
        return output
    except Exception as e:
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_err",
                tick=tick if tick is not None else 0, event_type="call", agent_id=agent_id,
                payload={"status": "error", "error": str(e), "model": model}))
        raise
```
（删除原有的 platform 分支，统一用 shutil.which）

- [ ] **Step 2: 手动验证 haiku + schema**（关键：MVP1 只实测 opus+schema，haiku 需确认）

```bash
cd D:/novel_test/docs/research && python -c "
import sys; sys.path.insert(0, '.')
from world_runtime.llm import call_llm
schema = {'type':'object','properties':{'word':{'type':'string'}},'required':['word']}
out = call_llm('说一个字', model='haiku', response_schema=schema)
print('TYPE:', type(out), 'VALUE:', out)
"
```
Expected: `TYPE: <class 'dict'> VALUE: {'word': '某字'}`。若 haiku 不支持 schema 或报错，报告 BLOCKED。

- [ ] **Step 3: 验证无 schema 仍兼容**（MVP1 行为不破坏）

```bash
cd D:/novel_test/docs/research && python -c "
import sys; sys.path.insert(0, '.')
from world_runtime.llm import call_llm
out = call_llm('回复一个字：好', model='haiku')
print('TYPE:', type(out), 'VALUE:', repr(out))
"
```
Expected: `TYPE: <class 'str'>`（result 字段，向后兼容）

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/llm.py
git commit -m "feat(world-runtime): call_llm response_schema (--json-schema structured_output)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: extractor 用 --json-schema

**Files:**
- Modify: `docs/research/world_runtime/extractor.py`

- [ ] **Step 1: 改 extractor**——定义 EFFECT_JSON_SCHEMA，用 response_schema，structured_output 直接是 dict。

替换 extract_effects_for_tick 实现（保留 EXTRACTOR_PROMPT、PRIORITY_MAP）：
```python
EFFECT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "set": {"type": "object", "default": {}},
                    "unset": {"type": "array", "items": {"type": "string"}, "default": []},
                    "intent": {"type": "string"},
                    "grounded": {"type": "boolean"},
                },
                "required": ["agent_id", "set", "intent", "grounded"],
            },
        }
    },
    "required": ["effects"],
}


def extract_effects_for_tick(actions: list[dict], snapshot, tick: int,
                              call_fn=call_llm, model: str = "haiku",
                              event_store=None) -> list[Effect]:
    """对一个 tick 的所有 NL action 提取 effect[]（用 --json-schema 强制结构）。"""
    from dataclasses import asdict
    snap_json = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
    actions_json = json.dumps(actions, ensure_ascii=False, indent=2)
    prompt = EXTRACTOR_PROMPT.format(snapshot_json=snap_json, actions_json=actions_json)

    result = call_fn(prompt, model=model, agent_id="_extractor", tick=tick,
                     event_store=event_store, response_schema=EFFECT_JSON_SCHEMA)

    # result 是 structured_output（dict，schema 合规）
    parsed = result if isinstance(result, dict) else json.loads(result)
    effects = []
    for e in parsed.get("effects", []):
        agent_type = next(
            (a["agent_type"] for a in actions if a.get("agent_id") == e.get("agent_id")),
            e.get("agent_type", "character"),
        )
        s = e.get("set", {}) or {}
        # unwrap nested dynamic（兜底，schema 已减罕）
        if isinstance(s, dict) and len(s) == 1 and "dynamic" in s and isinstance(s["dynamic"], dict):
            s = s["dynamic"]
        effects.append(Effect(
            agent_id=e.get("agent_id", ""),
            agent_type=agent_type,
            set=s,
            unset=e.get("unset", []),
            intent=e.get("intent", ""),
            grounded=e.get("grounded", True),
            priority=PRIORITY_MAP.get(agent_type, 1),
        ))
    return effects
```
删除原有的 `_parse_effects_json` / markdown 清理 / max_retries（schema 强制不再需要；若想保留兜底可留，但 MVP2 先简化）。

- [ ] **Step 2: 手动验证（小样本 + schema）**

```bash
cd D:/novel_test/docs/research && python -c "
import sys; sys.path.insert(0, '.')
from world_runtime.extractor import extract_effects_for_tick
from world_runtime.schemas import Snapshot
actions = [{'agent_id':'world_will','agent_type':'world_will','layer':'L3','nl_action':'释放封印将破征兆'}]
effs = extract_effects_for_tick(actions, Snapshot(), 0, model='haiku')
for e in effs:
    print('agent=',e.agent_id,'set=',e.set,'grounded=',e.grounded,'intent=',e.intent)
"
```
Expected: 打印 effect（schema 合规，无 JSON 解析问题）。

- [ ] **Step 3: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/extractor.py
git commit -m "feat(world-runtime): extractor uses --json-schema (constrained decoding)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: reducer 只 fold grounded=true

**Files:**
- Modify: `docs/research/world_runtime/reducer.py`
- Modify: `docs/research/world_runtime/tests/test_reducer.py`

- [ ] **Step 1: 追加失败测试**（test_reducer.py 末尾）

```python
def test_ungrounded_effect_not_folded():
    s0 = Snapshot()
    eff = Effect(agent_id="旁观者", set={"seal_state": "broken"},
                 intent="观察", grounded=False, priority=1)
    s1, _ = reducer([eff], s0)
    assert s1.seal_state == "intact"  # grounded=false 不 fold


def test_grounded_and_ungrounded_mixed():
    s0 = Snapshot()
    eff_g = Effect(agent_id="world_will", set={"seal_state": "weakening"},
                   intent="征兆", grounded=True, priority=4)
    eff_u = Effect(agent_id="旁观者", set={"seal_state": "broken"},
                   intent="观察", grounded=False, priority=1)
    s1, _ = reducer([eff_g, eff_u], s0)
    assert s1.seal_state == "weakening"  # 只 fold grounded，无冲突
```

- [ ] **Step 2: 运行验证失败**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/test_reducer.py::test_ungrounded_effect_not_folded -v
```
Expected: FAIL（当前 reducer fold 所有 effect）

- [ ] **Step 3: 改 reducer**——在 group by key 前过滤 grounded

在 reducer 函数开头（deepcopy 后，group by key 前）加过滤：
```python
    new_state = deepcopy(S_t)
    resolutions = []

    # 只 fold grounded=true（grounded=false 是意图层，保留 event 不 fold）
    grounded_effects = [e for e in effects if getattr(e, "grounded", True)]

    by_key = {}
    for eff in grounded_effects:
        for k, v in eff.set.items():
            by_key.setdefault(k, []).append((eff, v))
    # ...（后续逻辑不变，但用 grounded_effects 替代 effects 遍历 set/unset）
```
注意 unset 循环也改用 grounded_effects。

- [ ] **Step 4: 运行全部测试验证通过 + 无回归**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/ -v
```
Expected: PASS（28 原有 + 2 新 = 30）

- [ ] **Step 5: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/reducer.py docs/research/world_runtime/tests/test_reducer.py
git commit -m "feat(world-runtime): reducer only folds grounded effects (intent/event layering)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: integration test（mocked extract→reduce→snapshot，S1）

**Files:**
- Create: `docs/research/world_runtime/tests/test_integration.py`

- [ ] **Step 1: 写集成测试**（mock call_fn，不依赖真 LLM/临时 .output）

```python
from world_runtime.extractor import extract_effects_for_tick
from world_runtime.reducer import reducer
from world_runtime.schemas import Snapshot, Effect


def _mock_call_fn_factory(response: dict):
    """返回一个假的 call_fn，忽略 prompt 直接返回固定 structured_output。"""
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
    # 但 effect 仍存在（意图层保留）
    assert len(effects) == 1


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
```

- [ ] **Step 2: 运行验证通过**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/test_integration.py -v
```
Expected: PASS（3 passed）

- [ ] **Step 3: 跑全部测试无回归**

```bash
cd D:/novel_test/docs/research && python -m pytest world_runtime/tests/ -v
```
Expected: PASS（30 + 3 = 33）

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/tests/test_integration.py
git commit -m "test(world-runtime): integration test extract->reduce->snapshot (mocked, S1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 稳定性验证（跑 3 次）+ MVP2 报告

**Files:**
- Create: `docs/research/world_runtime/MVP2_REPORT.md`

- [ ] **Step 1: 跑 run_mvp1 3 次**（schema 后），每次存独立 events log

```bash
cd D:/novel_test/docs/research && for i in 1 2 3; do
  python -m world_runtime.run_mvp1 --model haiku 2>&1 | tail -5
  cp world_runtime/events.jsonl /tmp/mvp2_run$i.jsonl 2>/dev/null || cp world_runtime/events.jsonl world_runtime/run$i_events.jsonl
done
```
（Windows bash 可能不支持 /tmp，用 world_runtime/runN_events.jsonl）

- [ ] **Step 2: 比对 3 次 effect log 一致性**（Q1 稳定性）

```bash
cd D:/novel_test/docs/research/world_runtime && python -c "
import json
def loads(p):
    return [json.loads(l) for l in open(p,encoding='utf-8') if l.strip()]
runs = [loads(f'run{i}_events.jsonl') for i in (1,2,3)]
# 比较 effect event 的 (tick, agent_id, set, grounded)
def sig(runs):
    return [[(e['tick'], e['payload']['effect']['agent_id'], e['payload']['effect']['set'], e['payload']['effect']['grounded']) for e in run if e['event_type']=='effect'] for run in runs]
s = sig(runs)
print('run1 effects:', len(s[0]))
print('run1==run2:', s[0]==s[1])
print('run1==run3:', s[0]==s[2])
"
```
记录一致性结果。

- [ ] **Step 3: 看 grounded 分布**（Q2 分层）

```bash
cd D:/novel_test/docs/research/world_runtime && python -c "
import json
from collections import Counter
es = [json.loads(l) for l in open('events.jsonl',encoding='utf-8') if l.strip() and json.loads(l)['event_type']=='effect']
g = Counter(e['payload']['effect']['grounded'] for e in es)
print('grounded 分布:', dict(g))
print('意图层(false)比例:', g[False]/(g[True]+g[False]))
"
```

- [ ] **Step 4: 写 MVP2_REPORT.md**（带 Q1/Q2 回答）

```markdown
# MVP2 报告 — 稳定性 + 意图/事件分层

## Q1：--json-schema 消除了跨运行波动？
- [ ] 3 次 effect log 一致性：run1==run2? run1==run3?
- 对比 MVP1 的 48.5%→16.9% 波动

## Q2：grounded 分层清晰？
- [ ] grounded 分布（true/false 比例）
- [ ] grounded=false 的 intent 是否真是"观察/见证"类

## 改动
- call_llm response_schema（--json-schema constrained decoding）
- Effect grounded/agent_id/agent_type
- extractor schema 强制
- reducer 只 fold grounded
- integration test（S1）

## 测试
33 单测全过

## 判定
若 Q1 一致性高 → 稳定性解决，effect log 可复现
```
填完每个 `[ ]`。

- [ ] **Step 5: Commit**

```bash
cd D:/novel_test && git add docs/research/world_runtime/MVP2_REPORT.md docs/research/world_runtime/run*_events.jsonl
git commit -m "docs(world-runtime): MVP2 report - stability + layering verdict

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage**：--json-schema（Task 2/3）✓ / grounded 分层（Task 1/4）✓ / reducer fold grounded（Task 4）✓ / Q1 稳定性（Task 6）✓ / Q2 分层（Task 6）✓ / I1 agent_id（Task 1）✓ / S1 integration test（Task 5）✓

**Placeholder scan**：无 TBD/TODO，代码完整 ✓

**Type consistency**：Effect 字段（grounded/agent_id/agent_type）跨 Task 1/3/4/5 一致 ✓ / call_llm response_schema 跨 Task 2/3 一致 ✓ / reducer 用 grounded_effects 跨 Task 4 一致 ✓

---

## Execution

Plan saved to `docs/superpowers/plans/2026-06-13-world-runtime-mvp2.md`。延续 MVP1 的 subagent-driven 执行。
