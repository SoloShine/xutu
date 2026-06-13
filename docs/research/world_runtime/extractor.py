import json
import re
from dataclasses import asdict
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


def _parse_effects_json(raw: str) -> dict | None:
    """从 LLM 响应提取并解析 effects JSON。robust 处理 markdown 包裹 + 格式错误。
    返回解析后的 dict，或 None（彻底失败）。"""
    raw = raw.strip()
    # 去 markdown 包裹
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 正则提取第一个 {...}（DOTALL 跨行）
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def extract_effects_for_tick(actions: list[dict], snapshot, tick: int,
                              call_fn=call_llm, model: str = "haiku",
                              max_retries: int = 1) -> list[Effect]:
    """对一个 tick 的所有 NL action 提取 effect[]。失败重试 max_retries 次。

    actions: [{agent_id, agent_type, layer, nl_action}, ...]
    返回: [Effect, ...]
    """
    snap_json = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
    actions_json = json.dumps(actions, ensure_ascii=False, indent=2)
    prompt = EXTRACTOR_PROMPT.format(snapshot_json=snap_json, actions_json=actions_json)

    parsed = None
    for attempt in range(max_retries + 1):
        raw = call_fn(prompt, model=model, agent_id="_extractor", tick=tick)
        parsed = _parse_effects_json(raw)
        if parsed is not None:
            break
        # 重试时加一句强调
        prompt = prompt + "\n\n（上次输出无法解析为 JSON，请严格输出纯 JSON，确保所有字符串引号正确转义。）"

    if parsed is None:
        print(f"  WARN: tick {tick} extractor JSON 解析失败（{max_retries+1} 次尝试），跳过")
        return []

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