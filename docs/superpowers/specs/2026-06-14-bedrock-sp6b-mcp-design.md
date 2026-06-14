# 磐石 Bedrock SP6-B 设计：MCP Server（对话层即 UI）

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-B：MCP Server**。
> SP6-A（只读 CLI 工具集）✅ 已完成（export/diagnose/show-review-report/diff）。
> SP6-C（本地 Web UI）独立 spec。
> 前置：SP1-5 核心管线 + SP6-A 全部完成。

## 1. 目标与范围

SP6-A 把 bedrock 的只读能力暴露成 **CLI**（人敲命令）。SP6-B 把同样的能力暴露成 **MCP tool**——让对话层（Claude Code）能自然语言调用："查这卷体检""导出第三卷""这章 L2 过不过""这卷 review 哪些要人工判决"。UI 就是对话本身，无需为每个功能画控件。

**SP6-B 范围 = 1 个 FastMCP server + 8 个 MCP tool**：

| tool | 数据源（复用 SP6-A 纯函数层） |
|------|------------------------------|
| `export_project` | `do_export` |
| `diagnose` | `diagnose` |
| `show_review_report` | `show_review_report` |
| `diff_drift` | `detect_drift` + `render_drift_report` |
| `run_l2_check` | `run_l2`（live 重算信任锚，精简返回） |
| `get_chapter_flag` | `get_review_flag` + `compute_has_flag`（新抽出） |
| `list_volumes` | 直查 volume 表 |
| `list_chapters` | 直查 chapter 表 |

**不在 SP6-B 范围**：治理写入 tool（mark-*/unlock-volume）——那些是管线内部门禁信号，对话层随意写违背抗博弈；Web 可视化（SP6-C）；MCP transport 本身（用官方 SDK，非自研）；端到端 stdio 自动化测试。

## 2. 关键设计决策

- **MCP tool 直接调纯函数层**（`reader_commands.py` 函数 + `run_l2`/`get_review_flag`），不走 subprocess CLI。每 tool 内部 `get_connection(Path(project))` 独立开/关 conn。复用 SP6-A 已审核纯函数；支持跨项目（project 是参数）；与既有 novel_kg server 模式一致（server 薄、逻辑在 core）。
- **FastMCP + stdio transport**：`from mcp.server.fastmcp import FastMCP` + `@mcp.tool()`。`mcp[cli]>=1.0.0` 已是项目依赖（既有 novel_kg server 用）。
- **8 tool 全部只读或仅 export**（export 写 manifest + 文件，与 SP6-A 一致）。**不暴露治理写入**（mark-*/unlock-volume）。延续 SP6-A 只读精神 + 抗博弈。
- **入口**：`python -m src.bedrock.mcp_server`（cwd=workspaceFolder，**不**设 cwd=src）。与既有 bedrock 代码的 `from src.bedrock...` import 一致，零改造。详见 §4。
- **MCP 层 catch 异常转结构化错误**，绝不 SystemExit 崩 server（CLI 可 exit，server 必须稳）。详见 §6。
- **target 语义随 scope 变**：chapter scope 的 target=global_number（人类/LLM 友好），MCP 层内部 `_chapter_id` 转 id 喂纯函数；volume scope target=volume.id；book 无 target。对调用方透明。详见 §3。
- **`run_l2_check` 返回精简版**：只返回 hard_gate + violation 摘要，不含 advisory/metrics/drift 大对象（省 token，对话层够用）。详见 §3。
- **`compute_has_flag` 小重构**：把 `__main__.py` get-review-flag 里内联的 has_flag 派生逻辑抽到 `review_flag.py` 纯函数，MCP 和 CLI 共用（DRY）。详见 §5。

## 3. 8 个 MCP tool 规范

### 3.1 通用约定

- 所有 tool 首参 `project: str`（bedrock 项目目录的路径，该目录下有 bedrock.db）。**非名称**——与 bedrock CLI `--project` 语义一致，与旧 novel_kg server（用 name）不同。
- 每 tool 内部：校验 `(Path(project)/"bedrock.db").exists()` → 不存在则返回结构化错误（不创建空 db）；`conn = get_connection(Path(project))`；`try: ... finally: conn.close()`。
- 所有 tool 用统一错误处理 helper `_safe(conn_fn, ...)` 包裹（§6），catch 异常/SystemExit 转 `{"error": "..."}`。

### 3.2 tool 清单

**`export_project(project, scope, target=None, fmt="md", final=False) -> dict`**
- scope∈`"chapter"`/`"volume"`/`"book"`；target：chapter→global_number，volume→volume.id，book→忽略。
- MCP 层：chapter scope 时 `cid = _chapter_id(conn, target)`（global_number→id），再调 `do_export(conn, project, "chapter", cid, fmt, final, None)`。
- 返回 `{path, content_hash, chapter_count}`（ExportResult dataclass 转 dict）。

**`diagnose(project, scope, volume_id=None, with_l2=False) -> str`**
- scope∈`"volume"`/`"book"`；volume scope 时 volume_id 必填（volume.id）。
- MCP 层构造 `sc = ("volume", volume_id) if scope=="volume" else ("book", None)`，调 `diagnose(conn, project, sc, with_l2)`。
- 返回 markdown str。
- scope="book" + with_l2=True → diagnose 纯函数 SystemExit → MCP 层 catch 转结构化错误。

**`show_review_report(project, volume_id, escalate_only=False, plain=False) -> str`**
- 直接调 `show_review_report(project, volume_id, escalate_only, plain)`（纯文件读，不接 conn，但仍走 `_safe` 包裹 catch 文件缺失 SystemExit）。
- 返回 str。

**`diff_drift(project, scope, target=None, fmt="md", final=False) -> str`**
- target 解析同 export_project（chapter→global_number→id）。
- 调 `detect_drift(conn, project, scope_resolved, target_resolved, fmt, final)` + `render_drift_report(report, desc, fmt, final)`。
- 返回渲染好的 markdown str（含三路定位诊断）。
- desc：chapter→`f"ch{global_number}"`，volume→`f"vol(id={volume_id})"`，book→`"全书"`。

**`run_l2_check(project, global_number) -> dict`**
- 单章 live L2 重算（信任锚）。`cid = _chapter_id(conn, global_number)`；`report = run_l2(conn, cid)`。
- **精简返回**：`{passed_hard_gate: bool, violations_count: int, beat_violations: [{kind, beat_sequence, detail}, ...]}`。
- **不返回** advisory/metrics/drift（L2Report 的大字段，对话层用不上，省 token）。
- `beat_violations` 的 BeatViolation dataclass 转 dict（asdict）。

**`get_chapter_flag(project, global_number) -> dict`**
- `cid = _chapter_id(conn, global_number)`；`flag = get_review_flag(conn, cid)`。
- 返回 `{has_flag: bool, l2_unresolved, polish_broke_beat, forced_persist_failed, advisory_drift, likely_rule_or_model_issue}`。
- `has_flag` 由新抽的 `compute_has_flag(flag)` 计算（§5）。

**`list_volumes(project) -> list`**
- 直查：`SELECT id, number, name, chapter_start, chapter_end, volume_type FROM volume ORDER BY number`。
- 返回 list of dict。

**`list_chapters(project, volume_id=None) -> list`**
- volume_id 可选过滤。`SELECT id, global_number, title, status, volume_id FROM chapter [WHERE volume_id=?] ORDER BY global_number`。
- 返回 list of dict。

## 4. 入口与 .mcp.json 注册

### 4.1 入口

`src/bedrock/mcp_server.py` 末尾：
```python
if __name__ == "__main__":
    mcp.run()  # FastMCP 默认 stdio
```

启动：`python -m src.bedrock.mcp_server`（cwd=workspaceFolder，即 D:\novel_test）。

### 4.2 import 路径决策（关键）

`reader_commands.py` 现在用 `from src.bedrock.repositories...`（带 src 前缀，与既有 bedrock 代码一致）。MCP server 必须用同样的 import 才能复用。

- **不用** `.mcp.json` 的 `cwd=src` + `python -m bedrock.mcp_server`（旧 novel_kg server 那套）——那样 Python 顶层包是 `bedrock`，找不到 `src.bedrock`。
- **用** `python -m src.bedrock.mcp_server`（不设 cwd，默认 workspaceFolder）。与既有 `from src.bedrock...` import 完全一致，零改造。

### 4.3 .mcp.json 注册（SP6-B 完成后启用）

在既有 `.mcp.json` 的 `mcpServers` 下新增（**不 disable**，bedrock 是 V3 主线）：
```json
"bedrock": {
  "command": "python",
  "args": ["-m", "src.bedrock.mcp_server"]
}
```
- 不设 cwd（默认 workspaceFolder）。
- 旧 novel_kg server 保持 disabled。

## 5. compute_has_flag 重构

当前 `__main__.py` get-review-flag 命令内联了 has_flag 派生逻辑：
```python
advisory = flag.get("advisory_drift") or "{}"
has_flag = (flag.get("l2_unresolved",0)!=0 or flag.get("polish_broke_beat",0)!=0
            or flag.get("forced_persist_failed",0)!=0 or advisory not in (None,"{}"))
```

抽到 `src/bedrock/orchestration/review_flag.py`：
```python
def compute_has_flag(flag):
    """任一硬 flag != 0 或 advisory_drift 非空（'{}' 等价空）→ True。
    likely_rule_or_model_issue 不计入（l2_unresolved 的诊断子字段）。flag=None → False。"""
    if flag is None:
        return False
    advisory = flag.get("advisory_drift") or "{}"
    return (flag.get("l2_unresolved", 0) != 0
            or flag.get("polish_broke_beat", 0) != 0
            or flag.get("forced_persist_failed", 0) != 0
            or advisory not in (None, "{}"))
```

- `__main__.py` get-review-flag 改用 `compute_has_flag(flag)`（CLI 行为不变）。
- MCP `get_chapter_flag` 用同函数。
- 回归测试确认 CLI get-review-flag 输出不变。

## 6. 错误处理（CLI↔server 关键差异）

CLI 可 `sys.exit`（进程结束无所谓）；MCP server **绝不能崩**（崩了 Claude Code 断连）。

统一 helper：
```python
def _safe(tool_fn):
    """装饰 MCP tool：catch SystemExit/Exception → 返回 {"error": "..."}。"""
    @functools.wraps(tool_fn)
    def wrapper(*args, **kwargs):
        try:
            return tool_fn(*args, **kwargs)
        except SystemExit as e:
            return {"error": f"{type(e).__name__}: {e}"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper
```

- 每个 `@mcp.tool()` 函数体逻辑包在 `_safe` 内（或 tool 内部 try/except）。
- project 目录无 bedrock.db：tool 入口显式校验，返回 `{"error": f"项目目录无 bedrock.db：{project}"}`（**不创建空 db**——sqlite3.connect 会建空 db，需在 connect 前校验）。
- chapter global_number 不存在：`_chapter_id` 抛 SystemExit → `_safe` catch → 结构化错误。
- diagnose --book --with-l2 互斥：纯函数 SystemExit → catch → 结构化错误。

## 7. 架构与文件落点

```
src/bedrock/
├── mcp_server.py                       # 新增：FastMCP server + 8 tool + _safe helper
└── orchestration/review_flag.py        # 修改：抽出 compute_has_flag
tests/bedrock/
└── test_mcp_server.py                  # 新增：3 层测试
.mcp.json                               # 修改：新增 bedrock server（enabled）
```

`mcp_server.py` 结构：
```python
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from src.bedrock.db.connection import get_connection
from src.bedrock.cli.reader_commands import (
    do_export, diagnose as diagnose_fn, show_review_report as show_fn,
    detect_drift, render_drift_report,
)
from src.bedrock.orchestration.l2_pipeline import run_l2
from src.bedrock.orchestration.review_flag import get_review_flag, compute_has_flag
from dataclasses import asdict

mcp = FastMCP("bedrock", instructions="磐石 V3 小说管线只读工具集...")

DB_FILENAME = "bedrock.db"

def _chapter_id(conn, global_number): ...   # 复用 __main__ 的逻辑（或抽共享）

@mcp.tool()
def export_project(project: str, scope: str, target: int = None,
                   fmt: str = "md", final: bool = False) -> dict: ...

# ... 其余 7 个 tool ...

if __name__ == "__main__":
    mcp.run()
```

## 8. 测试策略

`tests/bedrock/test_mcp_server.py`。FastMCP `@mcp.tool()` 函数是普通 Python 函数，**直接调用测试**（不启 stdio transport）。

**层 1：tool 薄包装逻辑**（主体）：
- `test_export_project_chapter_resolves_global_number`：target=global_number → 内部转 id → do_export → 返回 `{path,content_hash,chapter_count}` + 文件生成
- `test_diagnose_tool_volume_scope`：scope="volume"+volume_id → markdown 含体检标记
- `test_diagnose_tool_book_with_l2_rejected`：scope="book"+with_l2=True → 结构化错误（不崩）
- `test_show_review_report_tool_escalate_only`：escalate_only=True → 返回 escalate 清单
- `test_diff_drift_tool_returns_rendered`：返回含"漂移检测"+三路定位 markdown
- `test_run_l2_check_returns_compact`：返回 `{passed_hard_gate, violations_count, beat_violations:[...]}`，**断言不含** advisory/metrics/drift 键
- `test_get_chapter_flag_has_flag_derived`：has_flag 由 compute_has_flag 正确派生
- `test_list_volumes` / `test_list_chapters`：返回结构正确，volume_id 过滤生效

**层 2：MCP 边界鲁棒性**（关键，CLI↔server 差异）：
- `test_missing_db_returns_structured_error`：project 目录无 bedrock.db → `{"error":...}`，不创建空 db，不崩
- `test_unknown_global_number_returns_structured_error`：global_number 不存在 → 结构化错误（不 SystemExit 崩）
- `test_tool_catches_exception_no_crash`：注入异常 → 结构化错误，server 存活

**层 3：has_flag 重构回归**：
- `test_compute_has_flag_logic`：compute_has_flag 各种组合（l2_unresolved=1→True；advisory_drift='{}'→False；非空→True；flag=None→False）
- `test_get_review_flag_cli_unchanged`：`__main__.py` get-review-flag 改用 compute_has_flag 后 CLI 行为不变（跑既有测试或新断言）

**不写的测试**：
- stdio transport 端到端（SDK 责任，非本项目逻辑）。
- 重复测纯函数层（SP6-A 已锁死）。

**手动冒烟**（SP6-B 完成后，不进自动化）：`python -m src.bedrock.mcp_server` 确认不崩；可选：用 mcp inspector 或 Claude Code 连上验证 tool 列表。

## 9. 与既有命令/系统的边界

- SP6-B MCP tool **复用** SP6-A 纯函数层，不重新实现业务逻辑。SP6-A 的抗博弈不变量（round-trip hash、manifest key 锁、diagnose 零写）自动继承。
- SP6-B 与旧 novel_kg server **独立**（不同 MCP server，不同 .mcp.json 条目，旧保持 disabled）。bedrock（V3）与 novel_kg（V1/V2）是不同系统，不互通。
- SP6-B **不替代** SP6-A CLI——CLI 仍可在终端直接用，MCP 是对话层入口，两者共用纯函数层。

## 10. 验收标准

- 8 个 MCP tool 各自可调用，全部只读或仅 export（写 manifest + 文件，与 SP6-A 一致）。
- MCP 层任何异常不崩 server（统一 `_safe` 转结构化错误）。
- project 目录无 bedrock.db → 结构化错误（不创建空 db）。
- `run_l2_check` 返回精简版（不含 advisory/metrics/drift）。
- `compute_has_flag` 重构后 CLI get-review-flag 行为不变。
- 零新依赖（`mcp[cli]` 既有，其余 stdlib + src.bedrock）。
- 全部测试通过（SP1-5 + SP6-A 既有 165 测试不受影响 + SP6-B 新增 ~14 测试）。
- `.mcp.json` 注册 bedrock server（enabled），手动冒烟 `python -m src.bedrock.mcp_server` 不崩。
