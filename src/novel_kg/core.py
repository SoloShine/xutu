"""
Novel KG 工具核心逻辑 — 模块化架构（V27）。

连接池 + 破坏性保护 + 43个业务函数。
从7个子模块导入并统一暴露，server.py（MCP）和 mcp_cli.py（CLI）共享此模块。

子模块：
- core_cache      : 目的检查缓存（SHA256）
- core_crud       : CRUD + 查询 + Prompt 组装
- core_compliance : 大纲合规检查（程序化+LLM语义+purpose）
- core_analysis   : 叙事节奏分析 + 编辑影响 + 大纲修订 + 后端同步
- core_parallel   : 并行章节生成（依赖分析→冻结上下文→合并）
- core_edits      : 事后编辑管理（快照/回滚/审核关卡）
- core_telemetry  : 遥测保存工具
"""

import os
import atexit

# ---- 路径基础设施 ----

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.normpath(os.path.join(_here, '..', '..'))
_projects_dir = os.environ.get('KG_PROJECTS_DIR') or os.path.join(_repo_root, 'projects')

from .config_loader import config_loader

# ---- 统一错误类（对外暴露） ----
from .core_errors import NovelKGError, UserError, SystemError, LogicError  # noqa: E402


# ========== 内部 LLM 开关 ==========

def _llm_enabled() -> bool:
    """内部 LLM 调用是否启用。默认关闭，设 NOVEL_LLM_ENABLED=1 开启。

    关闭时合规检查返回 needs_agent_review 标记，由 Agent 自行判定。
    开启时调 call_llm() 做语义/purpose 判定（需配置 LLM API）。
    """
    env = os.environ.get("NOVEL_LLM_ENABLED", "").strip()
    return env in ("1", "true", "yes")


# ========== 持久化辅助 ==========

def _persist(project: str, subdir: str, filename: str, content: str):
    """将内容落盘到 projects/<project>/<subdir>/<filename>。"""
    from datetime import datetime
    dir_path = os.path.join(_projects_dir, project, subdir)
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, filename)
    header = f"# Persisted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + content)


# ========== Bigram 工具 ==========

def _bigram_overlap_str(s1, s2, min_shared=2):
    """检查两个字符串是否有足够的bigram重叠"""
    if not s1 or not s2:
        return False
    def _bigrams(s):
        if len(s) < 4:
            return {s} if s else set()
        return {s[i:i+2] for i in range(len(s)-1)}
    return len(_bigrams(s1) & _bigrams(s2)) >= min_shared


# ============================================================
# Backend Selection
# ============================================================

_BACKEND = os.environ.get("KG_BACKEND", "json")  # "json"(默认) 或 "neo4j"


def _create_backend(project: str):
    """根据环境变量创建后端实例"""
    cfg = config_loader.load(project)
    if _BACKEND == "neo4j":
        from .graph import NovelKG
        return NovelKG(project=project, config=cfg)
    else:
        from .kg_json import JsonKG
        return JsonKG(project=project, data_dir=_projects_dir, config=cfg)


# ============================================================
# Connection Pool
# ============================================================

_pool: dict = {}


def _kg(project: str):
    """获取或创建连接池中的后端实例。首次访问时初始化遥测。"""
    if project not in _pool:
        _pool[project] = _create_backend(project)
        # V25: 懒初始化遥测 collector
        from . import telemetry as _tel
        if _tel._collector is None:
            _tel.init_telemetry(project)
    return _pool[project]


def close_all():
    """关闭所有池化连接。"""
    for kg in _pool.values():
        kg.close()
    _pool.clear()


atexit.register(close_all)


# ============================================================
# Destructive Operation Guard
# ============================================================

DESTRUCTIVE_CONFIRM = "I_UNDERSTAND_THIS_IS_DESTRUCTIVE"


def _check_destructive(confirm: str):
    """检查破坏性操作确认。返回 None 表示通过，返回 UserError 表示拒绝。"""
    if confirm != DESTRUCTIVE_CONFIRM:
        from .core_errors import UserError
        return UserError(
            f"破坏性操作已拦截。需传入 confirm='{DESTRUCTIVE_CONFIRM}' 以确认执行。",
            code="DESTRUCTIVE_BLOCKED"
        )
    return None


# ============================================================
# V27: 从子模块导入并暴露所有公共函数
# ============================================================

# -- 缓存层 --
from .core_cache import (  # noqa: E402
    purpose_cache_dir, purpose_cache_path, purpose_cache_hash,
    read_purpose_cache, write_purpose_cache, invalidate_purpose_cache,
)

# -- CRUD + 查询 + Prompt 组装 --
from .core_crud import (  # noqa: E402
    get_chapter_context, get_derivation_context, get_graph_stats,
    check_consistency, get_unresolved_threads, get_all_threads,
    get_extraction_prompt, get_writing_prompt, get_derivation_prompt,
    get_editing_prompt, init_project, add_character, add_location, add_event,
    add_chapter_arc, add_suspense_thread, add_outline_entry,
    add_style_guide, add_motif, add_theme, add_time_period,
    add_relation, update_suspense_thread, write_extraction,
    clear_chapter_data,
    get_boot_context, recall_thread, recall_arc, generate_context_digest,
    verify_pipeline_step, verify_chapter_complete,
    get_framework,
)

# -- 合规检查 --
from .core_compliance import (  # noqa: E402
    validate_chapter, detect_extraction_conflicts,
    check_outline_compliance, batch_check_outline_compliance,
)

# -- 分析 + 编辑影响 + 大纲修订 + 同步 --
from .core_analysis import (  # noqa: E402
    analyze_pacing, analyze_edit_impact, revise_outline, sync_backends,
)

# -- 并行章节生成 --
from .core_parallel import (  # noqa: E402
    analyze_parallel_groups, prepare_parallel_batch,
    get_parallel_writing_prompt, merge_parallel_results,
)

# -- 事后编辑管理 --
from .core_edits import (  # noqa: E402
    accept_edit, review_chapter, list_edits, rollback_edit,
)

# -- 遥测保存 --
from .core_telemetry import (  # noqa: E402
    save_telemetry_chapter_report, set_telemetry_wall_clock,
    save_telemetry_session_summary, inject_agent_phase,
    inject_chapter_metrics,
)


# ============================================================
# V25 遥测自动注入（无条件装饰，运行时通过 _collector 控制）
# ============================================================
from . import telemetry as _telemetry  # noqa: E402

_PUBLIC_TOOLS = [
    "get_chapter_context", "get_derivation_context", "get_graph_stats",
    "check_consistency", "get_unresolved_threads", "get_all_threads",
    "get_extraction_prompt", "get_writing_prompt", "get_derivation_prompt",
    "init_project", "add_character", "add_location", "add_event",
    "add_chapter_arc", "add_suspense_thread", "add_outline_entry",
    "add_style_guide", "add_motif", "add_theme", "add_time_period",
    "add_relation", "update_suspense_thread", "write_extraction",
    "clear_chapter_data", "validate_chapter", "detect_extraction_conflicts",
    "check_outline_compliance", "batch_check_outline_compliance",
    "sync_backends", "analyze_pacing", "revise_outline",
    "analyze_edit_impact", "accept_edit", "review_chapter",
    "list_edits", "rollback_edit", "analyze_parallel_groups",
    "prepare_parallel_batch", "get_parallel_writing_prompt",
    "merge_parallel_results",
    "save_telemetry_chapter_report", "save_telemetry_session_summary",
    "set_telemetry_wall_clock", "inject_agent_phase",
    "inject_chapter_metrics",
    "get_boot_context", "recall_thread", "recall_arc",
    "generate_context_digest",
    "verify_pipeline_step", "verify_chapter_complete",
    "get_framework",
]
for _fname in _PUBLIC_TOOLS:
    if _fname in globals():
        globals()[_fname] = _telemetry.wrap(globals()[_fname])
