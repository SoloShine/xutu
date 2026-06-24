# src/bedrock/runner/state.py
"""图状态(TypedDict)。纯数据——conn 不入态(sqlite 连接不可序列化/checkpoint),
经 build_graph(conn) 工厂闭包绑定到节点函数。"""
from typing import Any
from typing_extensions import TypedDict


class RunnerState(TypedDict):
    chapter_id: int
    chapter_global: int
    volume_id: int
    ctx: dict                  # boot context(beat 契约/正典/指纹/指令/范例/prev_tail)
    config: dict               # workflow_config merge 结果(caps/models/phases/prompts)
    prose: str                 # 当前章正文(LLM 产出;commit 后= DB 落盘版)
    report: dict               # 最新 L2 报告(信任锚):{passed_hard_gate, beat_violations, metrics}
    phase: str                 # 当前自纠阶段 "write"|"revise"——条件边据此回 write/revise,或前推
    iter: int                  # write 已迭代次数
    cap: int                   # writer cap(来自 config,默认 3)
    editor_iter: int           # revise(editor)已迭代次数
    editor_cap: int            # editor cap(来自 config caps.editor,默认 5)
    run_id: int                # workflow_run.id(可观测;0=未启)
    rejected: bool             # commit guard 拒绝(worklog/污染)→ 当前阶段重做信号
    violations_feedback: str   # 重做时附的 L2 违规反馈文本(write/revise 共用)
    result: dict               # 最终结果(status/passed/words/write_iter/editor_iter)
