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
- set: 该 agent 本 tick 对世界状态造成的**实际变化**（不是意图）。
- grounded: 这个 action 是否**真正落地为状态变化**。若 action 只是观察/见证/观望/陈述/程序性（如"召开会议""记录节点""校验合规"），grounded=false（意图层，不 fold）；若实际改变了世界状态，grounded=true。
- 若 grounded=false，set 应为空 {{}}，intent 注明意图。
- intent: 意图摘要（中文，给渲染层用）。
- priority 由 agent_type 决定，不要自己改。"""

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
                              call_fn=call_llm, model: str = "sonnet",
                              event_store=None) -> list[Effect]:
    """对一个 tick 的所有 NL action 提取 effect[]（用 --json-schema 强制结构）。

    model 默认 sonnet（haiku 不支持 --json-schema structured output）。
    """
    from dataclasses import asdict
    snap_json = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
    actions_json = json.dumps(actions, ensure_ascii=False, indent=2)
    prompt = EXTRACTOR_PROMPT.format(snapshot_json=snap_json, actions_json=actions_json)

    result = call_fn(prompt, model=model, agent_id="_extractor", tick=tick,
                     event_store=event_store, response_schema=EFFECT_JSON_SCHEMA)

    parsed = result if isinstance(result, dict) else json.loads(result)
    effects = []
    for e in parsed.get("effects", []):
        agent_type = next(
            (a["agent_type"] for a in actions if a.get("agent_id") == e.get("agent_id")),
            e.get("agent_type", "character"),
        )
        s = e.get("set", {}) or {}
        # unwrap nested dynamic（兜底）
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