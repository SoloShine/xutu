# 磐石 Bedrock SP6-B 设计：MCP Server（对话层即 UI）

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-B：MCP Server**。
> SP6-A（只读 CLI 工具集）✅ 已完成。SP6-C（本地 Web UI）独立 spec。
> 前置：SP1-5 核心管线 + SP6-A 全部完成。
>
> **修订记录**：经两路子代理对抗审核（复用真实性+FastMCP 交互 / 完备性+抗博弈+MCP 边界），已吸收 4 🔴 + 10 🟡。关键修订：beat_violations 字段改为真实 `{beat_id,kind,detail,fix_hint}`；`_safe` 改 tool 体内联 try/except（专抓 SystemExit，FastMCP 已兜 Exception）；export_project 显式声明不暴露 out（堵 path traversal）+ project 路径约束；scope+id 组合校验；_chapter_id 抽共享模块；.mcp.json 加 cwd；list_chapters join volume_number；补 tool docstring。

## 1. 目标与范围

SP6-A 把 bedrock 的只读能力暴露成 **CLI**（人敲命令）。SP6-B 把同样的能力暴露成 **MCP tool**——让对话层（Claude Code）能自然语言调用。UI 就是对话本身，无需为每个功能画控件。

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
| `list_chapters` | 直查 chapter 表 JOIN volume（带 volume_number） |

**不在 SP6-B 范围**：治理写入 tool（mark-*/unlock-volume）；Web 可视化（SP6-C）；MCP transport 自研（用官方 SDK）；端到端 stdio 自动化测试。

## 2. 关键设计决策

- **MCP tool 直接调纯函数层**（`reader_commands.py` 函数 + `run_l2`/`get_review_flag`），不走 subprocess CLI。每 tool 内部 `get_connection(Path(project))` 独立开/关 conn（`show_review_report` 例外，纯文件读不开 conn）。
- **FastMCP + stdio transport**：`from mcp.server.fastmcp import FastMCP` + `@mcp.tool()`。`mcp[cli]>=1.0.0` 已是项目依赖。
- **8 tool 全部只读或仅 export**。**不暴露治理写入**（mark-*/unlock-volume）。延续 SP6-A 抗博弈精神。
- **入口**：`python -m src.bedrock.mcp_server`（cwd=workspaceFolder，§4）。与既有 `from src.bedrock...` import 一致，零改造。
- **错误处理：tool 体内联 try/except 专抓 `SystemExit`**（§6 关键——FastMCP 的 `Tool.run` 已 `except Exception` 兜底普通异常，但 `SystemExit` 是 `BaseException` 子类穿透它会杀进程；纯函数层大量用 `raise SystemExit`/`sys.exit`，必须 MCP 层 catch）。
- **target 语义随 scope 变**：chapter scope target=global_number（MCP 层 `_chapter_id` 转 id），volume scope target=volume.id，book 无 target。scope+target 组合在 tool 入口显式校验（§3.2 R3）。
- **`export_project` 禁止暴露 `out` 参数**（path traversal 防御，§3.2 R2）；project 路径需在 workspace 内（§3.2 R2）。
- **`run_l2_check` 返回精简版**（§3.2，字段已核对真实 BeatViolation）。
- **`compute_has_flag` + `_chapter_id` 双重构**：两者都从 `__main__.py` 抽到纯函数层共享模块，CLI 和 MCP 共用，避免 mcp_server → `__main__` 逆向依赖（§5）。

## 3. 8 个 MCP tool 规范

### 3.1 通用约定

- 所有 tool 首参 `project: str`（bedrock 项目目录路径，该目录下有 bedrock.db）。**非名称**。
- **project 路径约束**（R2）：校验 `Path(project).resolve()` 必须在 workspace 根（`Path(os.environ.get("NOVEL_WORKSPACE", os.getcwd())).resolve()`）之下，拒绝 `..` 越界或 workspace 外绝对路径。返回 `{"error": "project 路径越界 workspace"}`。这是单用户本地工具，白名单根 = workspace，防 LLM 传任意系统路径。
- **db 存在性校验**：`(Path(project)/"bedrock.db").exists()` → 不存在返回 `{"error": f"项目目录无 bedrock.db：{project}"}`（**必须在 `get_connection` 之前**——`sqlite3.connect` 会创建空 db 文件）。不校验 schema 完整性（init_project 职责）。
- 每 tool（`show_review_report` 除外）内部 `conn = get_connection(Path(project))`；`try: ... finally: conn.close()`。WAL 模式（get_connection 已设）。
- **错误处理**：tool 体内联 `try/except (SystemExit, Exception)`（§6）。绝不崩 server。

### 3.2 tool 清单（含 docstring——LLM 据此选 tool）

**`export_project(project, scope, target=None, fmt="md", final=False) -> dict`**
- docstring：`"导出正文成稿（paragraph→文件，单向）。scope=chapter/volume/book；chapter 的 target=global_number，volume 的 target=volume.id，book 无 target。返回 {path,content_hash,chapter_count}。"`
- scope∈`chapter`/`volume`/`book`；target 语义随 scope（chapter→global_number，volume→volume.id，book→忽略）。
- **组合校验（R3）**：scope=chapter 且 target is None → `{"error":"scope=chapter 需 target(global_number)"}`；scope=volume 且 target is None → 同理。
- chapter scope：`cid = _chapter_id(conn, target)`（global_number→id）。
- **`out` 参数刻意不暴露**（R2 path traversal 防御）：强制传 `None` 给 `do_export`，文件只落在 `{project}/exports/`。**实现者勿以"灵活性"为由加回 out**——那会让 LLM 写到项目目录外任意路径。
- 返回 `{path (as_posix), content_hash, chapter_count}`。path 用 `Path(...).as_posix()`（跨平台/JSON 友好，避免 Windows 反斜杠转义坑）。

**`diagnose(project, scope, volume_id=None, with_l2=False) -> str`**
- docstring：`"体检报告（聚合管线留痕旗+章节状态+跨卷欠债）。默认 flag-only（快）；with_l2=True 对卷内每章现场跑 run_l2 重算（慢，逐章 CPU），仅当需对当前正文做独立信任检查时开。scope=volume 需 volume_id(volume.id)；scope=book 全书。返回 markdown。"`
- scope∈`volume`/`book`；**组合校验（R3）**：scope=volume 且 volume_id is None → `{"error":"scope=volume 需 volume_id"}`。
- 构造 `sc = ("volume", volume_id) if scope=="volume" else ("book", None)`，调 `diagnose` 纯函数。
- **with_l2 成本提示**（Y1）：instructions 引导 LLM 默认 `with_l2=False`；一卷十几章 with_l2 会逐章重算。
- 返回 markdown str。

**`show_review_report(project, volume_id, escalate_only=False, plain=False) -> str`**
- docstring：`"读 review_report_vol{volume_id}.md（SP5 生成的整卷回读报告）。escalate_only=True 只列需人工判决(escalate_human)项；plain=True 去 markdown 标记省 token。volume_id=volume.id。返回文本。"`
- **不开 conn**（纯文件读 `review_report_vol{volume_id}.md`）。仍走 try/except（catch 文件缺失 SystemExit）。
- 直接调 `show_review_report(project, volume_id, escalate_only, plain)`。
- 返回 str。

**`diff_drift(project, scope, target=None, fmt="md", final=False) -> str`**
- docstring：`"DB 段落与已导出文件的漂移检测（正文 SSOT 一致性）。三路 hash 定位是谁改了(DB改/文件改/两边)。scope=chapter/volume/book，target 同 export_project。final=True 比对 exports/final/ 定稿快照。返回 markdown。"`
- target 解析 + 组合校验同 export_project。
- 调 `detect_drift` + `render_drift_report`。desc：chapter→`f"ch{global_number}"`，volume→`f"vol(id={volume_id})"`，book→`"全书"`。
- 返回 markdown str。

**`run_l2_check(project, global_number) -> dict`**
- docstring：`"单章 beat 硬门禁 live 重算（信任锚，零 LLM）。回答'此刻 DB 正文过不过硬约束'。返回 {passed_hard_gate, violations_count, beat_violations}。"`
- `cid = _chapter_id(conn, global_number)`；`report = run_l2(conn, cid)`。
- **精简返回（字段已核对真实 BeatViolation，R1）**：`{passed_hard_gate: bool, violations_count: int, beat_violations: [{beat_id, kind, detail, fix_hint}, ...]}`。
  - BeatViolation 真实字段（`src/bedrock/checks/beat_fulfillment.py:11-16`）：`beat_id: int, kind: str, detail: str, fix_hint: str`。
  - kind 枚举：`unwritten_beat`/`missing_character`/`thread_not_advanced`。
  - 用 `asdict(v)` 转 dict，**不重命名字段**（避免 R1 重蹈）。
- **不返回** advisory/metrics/drift（L2Report 大字段，省 token）。

**`get_chapter_flag(project, global_number) -> dict`**
- docstring：`"查章节的留痕旗(chapter_review_flag 全字段)+派生 has_flag。has_flag=True 表示该章需 VolumeReview 复查。global_number=全局章号。"`
- `cid = _chapter_id(conn, global_number)`；`flag = get_review_flag(conn, cid)`。
- 返回：`flag` 是完整 dict（chapter_review_flag 全列：l2_unresolved/persisted_violations/likely_rule_or_model_issue/polish_broke_beat/forced_persist_failed/advisory_drift 等，get_review_flag 返回 dict(row)），**外加 `has_flag` 派生键**。
- `has_flag = compute_has_flag(flag)`（§5）。
- flag=None（章无旗行）时返回 `{"has_flag": False, "flag": None}`。

**`list_volumes(project) -> list`**
- docstring：`"列出全部卷(id/number/name/起止章/类型)，按卷号升序。"`
- `SELECT id, number, name, chapter_start, chapter_end, volume_type FROM volume ORDER BY number`。

**`list_chapters(project, volume_id=None) -> list`**
- docstring：`"列出章节(id/global_number/title/status/volume_id/volume_number/volume_name)，按 global_number 升序。volume_id 可选过滤到单卷。"`
- **JOIN volume 带出 volume_number/volume_name**（Y5，LLM 友好，免二次查）：`SELECT c.id, c.global_number, c.title, c.status, c.volume_id, v.number AS volume_number, v.name AS volume_name FROM chapter c JOIN volume v ON c.volume_id=v.id [WHERE c.volume_id=?] ORDER BY c.global_number`。

## 4. 入口与 .mcp.json 注册

### 4.1 入口

`src/bedrock/mcp_server.py` 末尾：
```python
if __name__ == "__main__":
    mcp.run()  # FastMCP 默认 stdio
```
启动：`python -m src.bedrock.mcp_server`（cwd=workspaceFolder）。

### 4.2 import 路径决策（已核实）

`reader_commands.py` 用 `from src.bedrock.repositories...`（带 src 前缀）。**用** `python -m src.bedrock.mcp_server`（不设 cwd=src）——与既有 import 一致，零改造。对比旧 novel_kg server 用相对 import `from . import core` + cwd=src，那是它自己的约定，bedrock 不跟随。

### 4.3 .mcp.json 注册（SP6-B 完成后启用，R-cwd）

在既有 `.mcp.json` 的 `mcpServers` 下新增（**不 disable**）：
```json
"bedrock": {
  "command": "python",
  "args": ["-m", "src.bedrock.mcp_server"],
  "cwd": "${workspaceFolder}"
}
```
- **显式 `cwd: ${workspaceFolder}`**（R-cwd，消除客户端 cwd 行为不确定性，让 `from src.bedrock...` 必然可解析）。
- 旧 novel_kg server 保持 disabled。

## 5. compute_has_flag + _chapter_id 双重构

### 5.1 compute_has_flag

当前 `__main__.py` get-review-flag 内联 has_flag 逻辑。抽到 `src/bedrock/orchestration/review_flag.py`：
```python
def compute_has_flag(flag):
    """任一硬 flag != 0 或 advisory_drift 非空('{}'.等价空) → True。
    likely_rule_or_model_issue 不计入(l2_unresolved 诊断子字段)。flag=None → False。"""
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

### 5.2 _chapter_id 抽共享（Y8/R-逆向依赖）

`_chapter_id` 当前在 `__main__.py`（`sys.exit` on not found）。mcp_server 若 `from src.bedrock.__main__ import _chapter_id` 会拉起整条 CLI 重依赖链（init_project/watchdog/cross_volume_gate 等）。抽到共享模块 `src/bedrock/db/chapter_lookup.py`：
```python
def chapter_id_by_global(conn, global_number):
    """global_number → chapter.id。找不到 raise SystemExit（MCP 层 _safe catch）。"""
    row = conn.execute("SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if row is None:
        raise SystemExit(f"找不到 global_number={global_number} 的章节")
    return row["id"]
```
- `__main__.py` 的 `_chapter_id` 改为调 `chapter_id_by_global`（或直接替换）。
- mcp_server import `from src.bedrock.db.chapter_lookup import chapter_id_by_global`。

## 6. 错误处理（CLI↔server 关键差异，R-SystemExit）

**核心事实（已核实 mcp 1.27.1）**：FastMCP 的 `Tool.run` 内部已 `except Exception as e: raise ToolError(...)`——普通 Exception 已被转成 MCP error response，**不会杀进程**。但 **`SystemExit` 是 `BaseException` 子类，不是 `Exception`**——FastMCP 的 `except Exception` **抓不住**。纯函数层大量用 `raise SystemExit`/`sys.exit`（`_chapter_id`、`diagnose` book+l2 互斥、`show_review_report` 文件缺失、`do_export` 空卷等）。**`SystemExit` 会穿透 FastMCP 杀掉 server 进程**。

**解决方案：tool 体内联 try/except（不用装饰器叠加）**。装饰器叠加虽技术可行（functools.wraps 保签名），但两审核员对是否破坏 schema 分歧，且装饰器顺序敏感——内联 try/except 无歧义、最稳。

每个 tool 体的业务逻辑包在 `try/except (SystemExit, Exception) as e: return {"error": f"{type(e).__name__}: {e}"}`：
```python
@mcp.tool()
def run_l2_check(project: str, global_number: int) -> dict:
    """单章 beat 硬门禁 live 重算（信任锚，零 LLM）。..."""
    try:
        if not _project_ok(project):
            return {"error": "..."}
        conn = get_connection(Path(project))
        try:
            cid = chapter_id_by_global(conn, global_number)
            report = run_l2(conn, cid)
            return _compact_l2(report)
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return {"error": f"{type(e).__name__}: {e}"}
```
- 返回类型注解保持 `dict`/`str`/`list`（FastMCP schema 生成靠 type hint + docstring，内联 try/except 不影响签名）。
- `_project_ok(project)` helper：workspace 路径约束 + db 存在性校验，返回 bool 或错误 str。

## 7. 架构与文件落点

```
src/bedrock/
├── mcp_server.py                       # 新增：FastMCP + 8 tool + _project_ok + _compact_l2
├── db/chapter_lookup.py                # 新增：chapter_id_by_global（从 __main__ 抽出）
└── orchestration/review_flag.py        # 修改：+ compute_has_flag
src/bedrock/__main__.py                 # 修改：get-review-flag 用 compute_has_flag；_chapter_id 用 chapter_id_by_global
tests/bedrock/
└── test_mcp_server.py                  # 新增：3 层测试
.mcp.json                               # 修改：+ bedrock server（enabled，cwd=workspaceFolder）
```

`mcp_server.py` 结构：
```python
import os
from pathlib import Path
from dataclasses import asdict
from mcp.server.fastmcp import FastMCP
from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.cli.reader_commands import (
    do_export, diagnose as diagnose_fn, show_review_report as show_fn,
    detect_drift, render_drift_report,
)
from src.bedrock.orchestration.l2_pipeline import run_l2
from src.bedrock.orchestration.review_flag import get_review_flag, compute_has_flag

mcp = FastMCP("bedrock", instructions=(
    "磐石 V3 小说管线只读工具集。导出成稿(export_project)、体检报告(diagnose 默认 flag-only 快、with_l2 慢)、"
    "读整卷回读报告(show_review_report)、正文漂移检测(diff_drift)、单章 L2 重算信任锚(run_l2_check)、"
    "查留痕旗(get_chapter_flag)、列卷章(list_volumes/list_chapters)。project=项目目录路径(含 bedrock.db)。"
))

def _project_ok(project):
    """workspace 路径约束 + db 存在性。返回 None(通过) 或 错误 str。"""
    ...

def _compact_l2(report):
    """L2Report → 精简 dict（passed_hard_gate + beat_violations[beat_id,kind,detail,fix_hint]）。"""
    return {
        "passed_hard_gate": report.passed_hard_gate,
        "violations_count": len(report.beat_violations),
        "beat_violations": [asdict(v) for v in report.beat_violations],
    }

@mcp.tool()
def export_project(...): ...
# ... 其余 7 tool ...

if __name__ == "__main__":
    mcp.run()
```

## 8. 测试策略

`tests/bedrock/test_mcp_server.py`。FastMCP `@mcp.tool()` 函数是普通 Python 函数，**直接调用测试**（不启 stdio）。

**层 1：tool 薄包装逻辑**：
- `test_export_project_chapter_resolves_global_number`：target=global_number → 内部转 id → 返回 `{path(as_posix),content_hash,chapter_count}` + 文件生成；**断言 path 用正斜杠**
- `test_diagnose_tool_volume_scope`：scope=volume+volume_id → markdown 含体检标记
- `test_show_review_report_tool_escalate_only`：escalate_only=True → escalate 清单
- `test_diff_drift_tool_returns_rendered`：含"漂移检测"+三路定位
- `test_run_l2_check_returns_compact`：返回 `{passed_hard_gate, violations_count, beat_violations}`；**断言 beat_violations[0] 含 beat_id/kind/detail/fix_hint 四键**（R1）；**断言无 advisory/metrics/drift 键**
- `test_get_chapter_flag_has_flag_derived`：has_flag 由 compute_has_flag 正确派生；flag=None → `{"has_flag":False,"flag":None}`
- `test_list_volumes`：结构正确
- `test_list_chapters_joins_volume_number`：返回含 volume_number/volume_name（Y5）；volume_id 过滤生效

**层 2：MCP 边界鲁棒性（R3/R2/崩）**：
- `test_scope_volume_missing_volume_id_returns_error`（R3）：scope=volume+volume_id=None → `{"error":...}`，不崩
- `test_scope_chapter_missing_target_returns_error`（R3）：scope=chapter+target=None → 结构化错误
- `test_export_project_out_not_exposed`（R2）：inspect export_project 签名断言**无 out 参数**
- `test_project_path_traversal_rejected`（R2）：project=`../etc` → `{"error":...}`
- `test_missing_db_returns_structured_error`：project 目录无 bedrock.db → `{"error":...}`，**不创建空 db**（断言目录无 bedrock.db 文件）
- `test_unknown_global_number_returns_structured_error`：global_number 不存在 → 结构化错误（SystemExit 被 catch，不崩）
- `test_tool_catches_systemexit_no_crash`：注入纯函数抛 SystemExit → `{"error":...}`，函数正常返回（server 存活）

**层 3：双重构回归**：
- `test_compute_has_flag_logic`：各组合（l2_unresolved=1→True；advisory_drift='{}'→False；非空→True；flag=None→False；likely_rule_or_model_issue=1 单独不计入）
- `test_chapter_id_by_global_shared`：chapter_id_by_global 正常返回 id；不存在 raise SystemExit
- `test_get_review_flag_cli_uses_compute_has_flag`（R-has_flag 回归）：直接调 `__main__.main` 跑 get-review-flag（或 subprocess `python -m src.bedrock get-review-flag`），断言输出 JSON 含正确 has_flag——**既有测试不覆盖 has_flag，必须新加此回归**

**不写**：stdio transport 端到端；重复测纯函数层（SP6-A 已锁）。
**手动冒烟**（完成后）：`python -m src.bedrock.mcp_server` 不崩；可选 mcp inspector / Claude Code 连上验 tool 列表。

## 9. 与既有命令/系统的边界

- SP6-B 复用 SP6-A 纯函数层，不重写业务逻辑。SP6-A 抗博弈不变量（round-trip hash、manifest key 锁、diagnose 零写）自动继承。
- SP6-B 与旧 novel_kg server **独立**（不同 .mcp.json 条目，旧 disabled）。
- SP6-B 不替代 SP6-A CLI——两者共用纯函数层。

## 10. 验收标准

- 8 个 MCP tool 各自可调用，全部只读或仅 export。
- **tool 体内联 try/except catch SystemExit，绝不崩 server**。
- project 路径越界 workspace / 无 bedrock.db → 结构化错误（不创建空 db）。
- scope+target 组合校验（volume 无 volume_id / chapter 无 target → 错误）。
- `export_project` 不暴露 `out`（path traversal 防御）。
- `run_l2_check` 返回精简版（beat_violations 含真实四字段 beat_id/kind/detail/fix_hint，无 advisory/metrics/drift）。
- `compute_has_flag` + `chapter_id_by_global` 抽共享模块后，CLI get-review-flag 行为不变（有回归测试）。
- 零新依赖（`mcp[cli]` 既有，其余 stdlib + src.bedrock）。
- 全部测试通过（SP1-5 + SP6-A 既有 165 不受影响 + SP6-B 新增 ~19 测试）。
- `.mcp.json` 注册 bedrock server（enabled，cwd=workspaceFolder），手动冒烟不崩。
