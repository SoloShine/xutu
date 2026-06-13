from dataclasses import dataclass, field
from typing import Literal, Any


@dataclass(frozen=True)
class Effect:
    """结构化状态增量（delta 风格，Fowler 教训）。"""
    agent_id: str = ""
    agent_type: str = "character"
    set: dict[str, Any] = field(default_factory=dict)
    unset: list[str] = field(default_factory=list)
    intent: str = ""
    grounded: bool = True       # True=事件层(fold) / False=意图层(保留不fold)
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
    dynamic: dict[str, Any] = field(default_factory=dict)
    # 未裁决矛盾（Wolf：同优先级冲突保留为燃料）
    unresolved_conflicts: list = field(default_factory=list)


# 预定义的强类型状态字段（reducer 校验这些；其余进 dynamic）
PREDEFINED_FIELDS = frozenset({
    "seal_state", "han_zheng_status", "lu_status",
    "squad_resolution", "network_resolution", "alliance_resolution",
    "alien_stance",
})


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
    conflicting: list[tuple[Effect, Any]]  # [(effect, value), ...]
    winner: tuple[Effect, Any] | None       # (effect, value) 或 None（未裁决）
    reason: str
    unresolved: bool

    # Note: winner/conflicting 在内存里持有 live Effect 引用，
    # 但 dataclasses.asdict() 序列化时会把嵌套 Effect 转成 dict
    # (downstream event store 读回时 winner[0] 是 dict 不是 Effect)
