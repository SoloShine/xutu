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