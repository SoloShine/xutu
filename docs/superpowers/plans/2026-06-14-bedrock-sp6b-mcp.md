# 磐石 Bedrock SP6-B 实现计划：MCP Server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 1 个 FastMCP server + 8 个 MCP tool，复用 SP6-A 纯函数层，对话层即 UI。

**Architecture:** 新增 `src/bedrock/mcp_server.py`（FastMCP + 8 tool + helpers）。先做两处重构（`chapter_id_by_global` + `compute_has_flag` 抽共享模块，CLI 改用），再建 server。tool 体内联 try/except 专抓 SystemExit（FastMCP 已兜 Exception）。

**Tech Stack:** `mcp[cli]>=1.0.0`（既有）+ stdlib + pytest。

**Spec:** `docs/superpowers/specs/2026-06-14-bedrock-sp6b-mcp-design.md`（两路对抗审核 4🔴+10🟡 已吸收）。

**关键不变量（贯穿）：**
- tool 体内联 `try/except (SystemExit, Exception)`，绝不崩 server。
- `_project_ok`：workspace 路径约束 + bedrock.db 存在性（connect 前校验，不创建空 db）。
- `export_project` 不暴露 `out`（path traversal 防御）。
- `run_l2_check` 返回精简版（beat_violations 真实四字段）。

---

## Task 1: 双重构（chapter_lookup + compute_has_flag）

**Files:**
- Create: `src/bedrock/db/chapter_lookup.py`
- Modify: `src/bedrock/orchestration/review_flag.py`（+ compute_has_flag）
- Modify: `src/bedrock/__main__.py`（_chapter_id + get-review-flag 改用共享函数）
- Test: `tests/bedrock/test_chapter_lookup.py`、`tests/bedrock/test_review_flag.py`（+has_flag 测试）、`tests/bedrock/test_cli_flag_regression.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_chapter_lookup.py（新建）
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def test_chapter_id_by_global_found(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=5, title="t")
    assert chapter_id_by_global(conn, 5) == cid
    conn.close()


def test_chapter_id_by_global_not_found_raises(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        chapter_id_by_global(conn, 999)
    conn.close()
```

```python
# 追加到 tests/bedrock/test_review_flag.py
from src.bedrock.orchestration.review_flag import compute_has_flag


def test_compute_has_flag_none():
    assert compute_has_flag(None) is False


def test_compute_has_flag_l2_unresolved():
    assert compute_has_flag({"l2_unresolved": 1, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}"}) is True


def test_compute_has_flag_advisory_empty():
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}"}) is False


def test_compute_has_flag_advisory_nonempty():
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0,
                             "advisory_drift": '{"dash_count": 99}'}) is True


def test_compute_has_flag_likely_rule_or_model_not_counted():
    """likely_rule_or_model_issue 单独不计入 has_flag（l2_unresolved 诊断子字段）。"""
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}",
                             "likely_rule_or_model_issue": 1}) is False
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_chapter_lookup.py tests/bedrock/test_review_flag.py::test_compute_has_flag_none -v` → FAIL（模块/函数未定义）

- [ ] **Step 3: 实现 chapter_lookup.py**

```python
# src/bedrock/db/chapter_lookup.py
"""共享 helper：global_number → chapter.id。CLI 与 MCP server 共用，避免 mcp_server 逆向依赖 __main__。"""


def chapter_id_by_global(conn, global_number):
    """global_number → chapter.id。找不到 raise SystemExit（CLI 直接退出 / MCP 层 try-except catch）。"""
    row = conn.execute(
        "SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if row is None:
        raise SystemExit(f"找不到 global_number={global_number} 的章节")
    return row["id"]
```

- [ ] **Step 4: 实现 compute_has_flag（追加到 review_flag.py）**

```python
# 追加到 src/bedrock/orchestration/review_flag.py
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

- [ ] **Step 5: 重构 __main__.py**

(a) `_chapter_id`（__main__.py:26-32）改为调共享函数：
```python
from src.bedrock.db.chapter_lookup import chapter_id_by_global

def _chapter_id(conn, global_number):
    """global_number → chapter.id（委托共享函数，保 CLI 友好报错）。"""
    return chapter_id_by_global(conn, global_number)
```
（保留 `_chapter_id` 名以免改所有调用点；或直接删 `_chapter_id` 定义、所有 `cid = _chapter_id(...)` 改 `chapter_id_by_global(...)`——选保留薄包装，改动最小。）

(b) get-review-flag 分支（__main__.py:274-288）的 has_flag 内联（:280-286）替换为：
```python
        elif args.cmd == "get-review-flag":
            cid = _chapter_id(conn, args.chapter)
            flag = get_review_flag(conn, cid)
            has_flag = compute_has_flag(flag)
            print(json.dumps({"has_flag": has_flag, "flag": flag},
                             ensure_ascii=False, default=str))
```
顶部 import 加 `from src.bedrock.orchestration.review_flag import compute_has_flag`（get_review_flag 已 import，同模块，合并到既有 import 行）。

- [ ] **Step 6: CLI has_flag 回归测试（新建）**

```python
# tests/bedrock/test_cli_flag_regression.py（新建）
import json
import sys
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter
from src.bedrock.orchestration.review_flag import mark_unresolved


def test_get_review_flag_cli_has_flag_output(tmp_project, capsys):
    """重构后 CLI get-review-flag 输出 JSON 仍含正确 has_flag。"""
    from src.bedrock.__main__ import main
    from src.bedrock.checks.beat_fulfillment import BeatViolation
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    mark_unresolved(conn, cid, [BeatViolation(beat_id=1, kind="unwritten_beat",
                                              detail="d", fix_hint="h")],
                    likely_rule_or_model_issue=False)
    conn.commit()
    conn.close()
    old = sys.argv
    sys.argv = ["bedrock", "get-review-flag", "--project", str(tmp_project), "--chapter", "1"]
    try:
        main()
    finally:
        sys.argv = old
    out = json.loads(capsys.readouterr().out)
    assert out["has_flag"] is True       # l2_unresolved=1 → has_flag True
    assert out["flag"]["l2_unresolved"] == 1
```

- [ ] **Step 7: 跑测试 + 全量回归**

`python -m pytest tests/bedrock/ 2>&1 | tail -5` → SP1-5 + SP6-A 165 全过 + 新增测试过

- [ ] **Step 8: Commit**

```bash
git add src/bedrock/db/chapter_lookup.py src/bedrock/orchestration/review_flag.py src/bedrock/__main__.py tests/bedrock/test_chapter_lookup.py tests/bedrock/test_review_flag.py tests/bedrock/test_cli_flag_regression.py
git commit -m "refactor(bedrock): 抽 chapter_id_by_global + compute_has_flag 共享 (SP6-B 前置)"
```

---

## Task 2: mcp_server.py scaffold + 4 tools

**Files:** Create `src/bedrock/mcp_server.py`、`tests/bedrock/test_mcp_server.py`

- [ ] **Step 1: 写失败测试（scaffold + 4 tool）**

```python
# tests/bedrock/test_mcp_server.py（新建）
import inspect
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_paragraph,
)
from src.bedrock.repositories.worldbook import add_constant
from src.bedrock.mcp_server import (
    export_project, diagnose, show_review_report, list_volumes,
)


def _seed(conn):
    v1 = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    c1 = create_chapter(conn, volume_id=v1, global_number=1, title="甲", status="completed")
    create_paragraph(conn, chapter_id=c1, seq=1, text="正文甲",
                     content_hash="h1", beat_id=None, role="narration")
    add_constant(conn, key="work_name", value="测试书")
    return v1, c1


def test_export_project_chapter(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=1, fmt="md")
    assert "path" in result and "content_hash" in result and "chapter_count" in result
    assert Path(result["path"]).exists()
    assert "/" in result["path"] or "\\" in result["path"]   # path 是字符串
    assert result["chapter_count"] == 1


def test_export_project_path_uses_posix(tmp_project):
    """path 用 as_posix（正斜杠），即使 Windows。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=1)
    assert "\\" not in result["path"]    # POSIX 正斜杠


def test_export_project_out_not_exposed():
    """R2：export_project 签名无 out 参数（path traversal 防御）。"""
    sig = inspect.signature(export_project)
    assert "out" not in sig.parameters


def test_diagnose_tool_volume(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    report = diagnose(str(tmp_project), scope="volume", volume_id=v1)
    assert "体检模式标记" in report
    assert "flag-only" in report


def test_diagnose_tool_volume_missing_id_returns_error(tmp_project):
    """R3：scope=volume + volume_id=None → 结构化错误，不崩。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = diagnose(str(tmp_project), scope="volume", volume_id=None)
    assert isinstance(result, dict) and "error" in result


def test_show_review_report_tool(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text(
        "# VolumeReview 报告 — 卷 1\n\n## 修正结果（三状态）\n- ch1: escalate_human\n",
        encoding="utf-8")
    out = show_review_report(str(tmp_project), volume_id=1, escalate_only=True)
    assert "ch1" in out


def test_list_volumes_tool(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    vols = list_volumes(str(tmp_project))
    assert len(vols) == 1
    assert vols[0]["number"] == 1
    assert vols[0]["name"] == "第一卷"
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_mcp_server.py -v` → FAIL（mcp_server 未定义）

- [ ] **Step 3: 实现 mcp_server.py（scaffold + 4 tool）**

```python
# src/bedrock/mcp_server.py
"""磐石 Bedrock MCP Server：把只读能力暴露给对话层（Claude Code）。复用 SP6-A 纯函数层。
8 tool 全部只读或仅 export。tool 体内联 try/except 专抓 SystemExit（FastMCP 已兜 Exception，
但 SystemExit 是 BaseException 子类穿透它杀进程；纯函数层大量 raise SystemExit）。
不暴露治理写入（mark-*/unlock-volume）——抗博弈。"""
import os
from pathlib import Path
from dataclasses import asdict
from mcp.server.fastmcp import FastMCP

from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.cli.reader_commands import (
    do_export, diagnose as diagnose_fn, show_review_report as show_fn,
)
from src.bedrock.orchestration.review_flag import get_review_flag, compute_has_flag

mcp = FastMCP("bedrock", instructions=(
    "磐石 V3 小说管线只读工具集。导出成稿(export_project)、体检报告"
    "(diagnose 默认 flag-only 快、with_l2 慢)、读整卷回读报告(show_review_report)、"
    "正文漂移检测(diff_drift)、单章 L2 重算信任锚(run_l2_check)、查留痕旗"
    "(get_chapter_flag)、列卷章(list_volumes/list_chapters)。project=项目目录路径(含 bedrock.db)。"
))


def _project_ok(project):
    """workspace 路径约束 + bedrock.db 存在性。返回 None(通过) 或 错误 str。
    必须在 get_connection 之前调用（sqlite3.connect 会创建空 db）。"""
    try:
        p = Path(project).resolve()
    except (OSError, ValueError) as e:
        return f"无效路径: {e}"
    workspace = Path(os.environ.get("NOVEL_WORKSPACE", os.getcwd())).resolve()
    try:
        p.relative_to(workspace)
    except ValueError:
        return f"project 路径越界 workspace: {project}"
    if not (p / "bedrock.db").exists():
        return f"项目目录无 bedrock.db: {project}"
    return None


def _open_conn(project):
    """_project_ok 通过后开 conn。调用方负责 finally close。"""
    return get_connection(Path(project))


@mcp.tool()
def export_project(project: str, scope: str, target: int = None,
                   fmt: str = "md", final: bool = False) -> dict:
    """导出正文成稿（paragraph→文件，单向）。scope=chapter/volume/book；
    chapter 的 target=global_number，volume 的 target=volume.id，book 无 target。
    返回 {path,content_hash,chapter_count}。"""
    try:
        err = _project_ok(project)
        if err:
            return {"error": err}
        if scope in ("chapter", "volume") and target is None:
            return {"error": f"scope={scope} 需 target"}
        conn = _open_conn(project)
        try:
            if scope == "chapter":
                cid = chapter_id_by_global(conn, target)
                t = cid
            elif scope == "volume":
                t = target
            else:  # book
                t = None
            result = do_export(conn, project, scope, t, fmt, final, None)  # out 强制 None
            return {"path": Path(result.path).as_posix(),
                    "content_hash": result.content_hash,
                    "chapter_count": result.chapter_count}
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def diagnose(project: str, scope: str, volume_id: int = None,
             with_l2: bool = False) -> str:
    """体检报告（聚合管线留痕旗+章节状态+跨卷欠债）。默认 flag-only（快）；
    with_l2=True 对卷内每章现场跑 run_l2 重算（慢，逐章 CPU），仅当需对当前正文做独立
    信任检查时开。scope=volume 需 volume_id(volume.id)；scope=book 全书。返回 markdown。"""
    try:
        err = _project_ok(project)
        if err:
            return json_error(err)
        if scope == "volume" and volume_id is None:
            return json_error("scope=volume 需 volume_id")
        conn = _open_conn(project)
        try:
            sc = ("volume", volume_id) if scope == "volume" else ("book", None)
            return diagnose_fn(conn, project, sc, with_l2)
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return json_error(f"{type(e).__name__}: {e}")


def json_error(msg):
    """统一错误返回（str 类 tool 也用 JSON 字符串，便于对话层解析）。"""
    import json
    return json.dumps({"error": msg}, ensure_ascii=False)


@mcp.tool()
def show_review_report(project: str, volume_id: int,
                       escalate_only: bool = False, plain: bool = False) -> str:
    """读 review_report_vol{volume_id}.md（SP5 生成的整卷回读报告）。
    escalate_only=True 只列需人工判决(escalate_human)项；plain=True 去 markdown 省token。"""
    try:
        err = _project_ok(project)   # 仍校验项目（文件在项目目录下）
        if err:
            return json_error(err)
        return show_fn(project, volume_id, escalate_only, plain)   # 纯文件读，不开 conn
    except (SystemExit, Exception) as e:
        return json_error(f"{type(e).__name__}: {e}")


@mcp.tool()
def list_volumes(project: str) -> list:
    """列出全部卷(id/number/name/起止章/类型)，按卷号升序。"""
    try:
        err = _project_ok(project)
        if err:
            return [{"error": err}]
        conn = _open_conn(project)
        try:
            rows = conn.execute(
                "SELECT id, number, name, chapter_start, chapter_end, volume_type "
                "FROM volume ORDER BY number").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


if __name__ == "__main__":
    mcp.run()
```

注意：`diagnose`/`show_review_report` 的返回类型注解是 `str`（纯函数返回 markdown str），但错误时返回 JSON 字符串（`json_error`）。`list_volumes` 返回 `list`，错误时返回 `[{"error":...}]`。`export_project` 返回 `dict`。

- [ ] **Step 4: 跑测试**

`python -m pytest tests/bedrock/test_mcp_server.py -v` → Step1 的 7 测试过

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/mcp_server.py tests/bedrock/test_mcp_server.py
git commit -m "feat(bedrock): SP6-B mcp_server scaffold + 4 tool (export/diagnose/show/list_volumes)"
```

---

## Task 3: 剩余 4 tools（diff_drift/run_l2_check/get_chapter_flag/list_chapters）

**Files:** Modify `src/bedrock/mcp_server.py`、`tests/bedrock/test_mcp_server.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_mcp_server.py
from src.bedrock.mcp_server import diff_drift, run_l2_check, get_chapter_flag, list_chapters
from src.bedrock.cli.reader_commands import do_export


def test_diff_drift_tool(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    conn.close()
    out = diff_drift(str(tmp_project), scope="chapter", target=1)
    assert "漂移检测" in out


def test_run_l2_check_returns_compact(tmp_project):
    """R1：beat_violations 含真实四字段 beat_id/kind/detail/fix_hint；无 advisory/metrics/drift。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = run_l2_check(str(tmp_project), global_number=1)
    assert "passed_hard_gate" in result
    assert "violations_count" in result
    assert "beat_violations" in result
    assert isinstance(result["beat_violations"], list)
    # 若有 violation，断言四字段
    if result["beat_violations"]:
        v0 = result["beat_violations"][0]
        assert {"beat_id", "kind", "detail", "fix_hint"} <= set(v0.keys())
    # 精简：不含大字段
    assert "advisory" not in result
    assert "metrics" not in result
    assert "drift" not in result


def test_get_chapter_flag_no_flag(tmp_project):
    """章无旗行 → {has_flag:False, flag:None}。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = get_chapter_flag(str(tmp_project), global_number=1)
    assert result["has_flag"] is False
    assert result["flag"] is None


def test_get_chapter_flag_with_flag(tmp_project):
    from src.bedrock.orchestration.review_flag import mark_unresolved
    from src.bedrock.checks.beat_fulfillment import BeatViolation
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    mark_unresolved(conn, c1, [BeatViolation(beat_id=1, kind="unwritten_beat",
                                             detail="d", fix_hint="h")],
                    likely_rule_or_model_issue=False)
    conn.commit()
    conn.close()
    result = get_chapter_flag(str(tmp_project), global_number=1)
    assert result["has_flag"] is True
    assert result["flag"]["l2_unresolved"] == 1


def test_list_chapters_joins_volume_number(tmp_project):
    """Y5：list_chapters 返回含 volume_number/volume_name。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    chs = list_chapters(str(tmp_project))
    assert len(chs) == 1
    assert chs[0]["global_number"] == 1
    assert chs[0]["volume_number"] == 1
    assert chs[0]["volume_name"] == "第一卷"


def test_list_chapters_volume_filter(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    v2 = create_volume(conn, 2, "第二卷", 3, 4, "climax")
    create_chapter(conn, volume_id=v2, global_number=3, title="乙", status="planned")
    conn.close()
    chs = list_chapters(str(tmp_project), volume_id=v2)
    assert len(chs) == 1
    assert chs[0]["global_number"] == 3
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_mcp_server.py -k "diff_drift or run_l2_check or get_chapter_flag or list_chapters" -v` → FAIL（4 tool 未定义）

- [ ] **Step 3: 追加 4 tool 到 mcp_server.py**

```python
# 顶部 import 补充
from src.bedrock.cli.reader_commands import detect_drift, render_drift_report
from src.bedrock.orchestration.l2_pipeline import run_l2


# 追加 tool（list_volumes 之后、if __name__ 之前）

@mcp.tool()
def diff_drift(project: str, scope: str, target: int = None,
               fmt: str = "md", final: bool = False) -> str:
    """DB 段落与已导出文件的漂移检测（正文 SSOT 一致性）。三路 hash 定位是谁改了
    (DB改/文件改/两边)。scope=chapter/volume/book，target 同 export_project。
    final=True 比对 exports/final/ 定稿快照。返回 markdown。"""
    try:
        err = _project_ok(project)
        if err:
            return json_error(err)
        if scope in ("chapter", "volume") and target is None:
            return json_error(f"scope={scope} 需 target")
        conn = _open_conn(project)
        try:
            if scope == "chapter":
                cid = chapter_id_by_global(conn, target)
                t, desc = cid, f"ch{target}"
            elif scope == "volume":
                t, desc = target, f"vol(id={target})"
            else:
                t, desc = None, "全书"
            report = detect_drift(conn, project, scope, t, fmt, final)
            return render_drift_report(report, desc, fmt, final)
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return json_error(f"{type(e).__name__}: {e}")


@mcp.tool()
def run_l2_check(project: str, global_number: int) -> dict:
    """单章 beat 硬门禁 live 重算（信任锚，零 LLM）。回答'此刻 DB 正文过不过硬约束'。
    返回 {passed_hard_gate, violations_count, beat_violations:[{beat_id,kind,detail,fix_hint}]}。"""
    try:
        err = _project_ok(project)
        if err:
            return {"error": err}
        conn = _open_conn(project)
        try:
            cid = chapter_id_by_global(conn, global_number)
            report = run_l2(conn, cid)
            return {
                "passed_hard_gate": report.passed_hard_gate,
                "violations_count": len(report.beat_violations),
                "beat_violations": [asdict(v) for v in report.beat_violations],
            }
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def get_chapter_flag(project: str, global_number: int) -> dict:
    """查章节的留痕旗(chapter_review_flag 全字段)+派生 has_flag。has_flag=True 表示
    该章需 VolumeReview 复查。global_number=全局章号。"""
    try:
        err = _project_ok(project)
        if err:
            return {"error": err}
        conn = _open_conn(project)
        try:
            cid = chapter_id_by_global(conn, global_number)
            flag = get_review_flag(conn, cid)
            return {"has_flag": compute_has_flag(flag), "flag": flag}
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def list_chapters(project: str, volume_id: int = None) -> list:
    """列出章节(id/global_number/title/status/volume_id/volume_number/volume_name)，
    按 global_number 升序。volume_id 可选过滤到单卷。"""
    try:
        err = _project_ok(project)
        if err:
            return [{"error": err}]
        conn = _open_conn(project)
        try:
            if volume_id is not None:
                rows = conn.execute(
                    "SELECT c.id, c.global_number, c.title, c.status, c.volume_id, "
                    "v.number AS volume_number, v.name AS volume_name "
                    "FROM chapter c JOIN volume v ON c.volume_id=v.id "
                    "WHERE c.volume_id=? ORDER BY c.global_number", (volume_id,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT c.id, c.global_number, c.title, c.status, c.volume_id, "
                    "v.number AS volume_number, v.name AS volume_name "
                    "FROM chapter c JOIN volume v ON c.volume_id=v.id "
                    "ORDER BY c.global_number").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return [{"error": f"{type(e).__name__}: {e}"}]
```

注意 `diff_drift`/`run_l2_check`/`get_chapter_flag`/`list_chapters` 与 Step 1 测试 import 的名字一致。`render_drift_report`、`detect_drift`、`run_l2` 需在顶部 import。

- [ ] **Step 4: 跑测试**

`python -m pytest tests/bedrock/test_mcp_server.py -v` → 全过（Task2 的 7 + Task3 的 6 = 13）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/mcp_server.py tests/bedrock/test_mcp_server.py
git commit -m "feat(bedrock): SP6-B 剩余4 tool (diff_drift/run_l2_check/get_chapter_flag/list_chapters)"
```

---

## Task 4: MCP 边界鲁棒性测试（§8 层 2）

**Files:** Modify `tests/bedrock/test_mcp_server.py`

- [ ] **Step 1: 追加边界测试**

```python
# 追加到 tests/bedrock/test_mcp_server.py
from src.bedrock.mcp_server import _project_ok


def test_project_path_traversal_rejected(tmp_project):
    """R2：project 路径越界 workspace → 错误。"""
    err = _project_ok("../../etc")
    assert err and "越界" in err


def test_missing_db_returns_structured_error(tmp_project, tmp_path):
    """目录无 bedrock.db → 错误，且不创建空 db。"""
    empty_dir = tmp_path / "empty_proj"
    empty_dir.mkdir()
    result = export_project(str(empty_dir), scope="book")
    assert "error" in result
    assert not (empty_dir / "bedrock.db").exists()   # 不创建空 db


def test_unknown_global_number_returns_structured_error(tmp_project):
    """global_number 不存在 → SystemExit 被 catch → 结构化错误，不崩。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = run_l2_check(str(tmp_project), global_number=999)
    assert "error" in result


def test_scope_chapter_missing_target_returns_error(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=None)
    assert "error" in result and "target" in result["error"]


def test_tool_catches_exception_no_crash(tmp_project, monkeypatch):
    """注入纯函数抛异常 → 结构化错误，函数正常返回（server 存活）。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    import src.bedrock.mcp_server as ms
    def boom(*a, **k):
        raise RuntimeError("injected")
    monkeypatch.setattr(ms, "do_export", boom)
    result = export_project(str(tmp_project), scope="chapter", target=1)
    assert "error" in result and "injected" in result["error"]
```

注意：`test_project_path_traversal_rejected` 用相对路径 `../../etc`——`_project_ok` 里 `Path("../../etc").resolve()` 会解析成 workspace 外，`relative_to(workspace)` 抛 ValueError → 返回越界错误。但 tmp_project 自身在 tmp_path 下（pytest tmp），workspace=os.getcwd()（测试跑时的 cwd=D:\novel_test）。`../../etc` 从 cwd 解析会到 D:\etc 之类，确实越界 D:\novel_test。OK。但需确认 NOVEL_WORKSPACE 未设时 fallback os.getcwd()。测试里 monkeypatch 可设 NOVEL_WORKSPACE=tmp_project 让边界更确定（可选）。

- [ ] **Step 2: 跑测试**

`python -m pytest tests/bedrock/test_mcp_server.py -v` → 全过（13 + 5 = 18）

- [ ] **Step 3: Commit**

```bash
git add tests/bedrock/test_mcp_server.py
git commit -m "test(bedrock): SP6-B MCP 边界鲁棒性 (path traversal/missing db/SystemExit catch)"
```

---

## Task 5: .mcp.json 注册 + 冒烟 + 全量回归 + 最终复核

**Files:** Modify `.mcp.json`

- [ ] **Step 1: 修改 .mcp.json**

在既有 `mcpServers` 下加（保留旧 novel_kg disabled 不动）：
```json
"bedrock": {
  "command": "python",
  "args": ["-m", "src.bedrock.mcp_server"],
  "cwd": "${workspaceFolder}"
}
```

- [ ] **Step 2: 手动冒烟（确认 server 能启）**

```bash
cd D:/novel_test
timeout 3 python -m src.bedrock.mcp_server < /dev/null; echo "exit=$?"
```
Expected: 进程启动不立即崩（stdio 等输入，timeout 3s 后退出，exit 非零是正常——它等 stdin）。若 import 报错会立刻崩并打印 traceback——那种 exit 是失败。确认无 traceback。

更可靠：`python -c "from src.bedrock.mcp_server import mcp; print('tools:', [t for t in dir()])"` 或 `python -c "import src.bedrock.mcp_server as m; print('ok', m.mcp.name)"`。

- [ ] **Step 3: 全量回归**

`cd D:/novel_test && python -m pytest tests/bedrock/ 2>&1 | tail -5`
Expected: SP1-5 + SP6-A 165 + SP6-B 新增（~19 chapter_lookup/review_flag/cli_flag/mcp_server）全过，2 e2e skip。

- [ ] **Step 4: 派最终复核子代理**

用 superpowers:code-reviewer 派子代理审 `src/bedrock/mcp_server.py` + 重构后的 `__main__.py` + `chapter_lookup.py` + `review_flag.py`，对照 spec §10 验收 + 抗博弈（tool 不崩 server / 不暴露 out / project 约束 / SystemExit catch / 精简返回 / 双重构 DRY）。问题→修→复核。

- [ ] **Step 5: 更新项目记忆**

更新 `bedrock-v3-status.md`：SP6-B ✅ 完成。

- [ ] **Step 6: Commit**

```bash
git add .mcp.json
git commit -m "feat(bedrock): SP6-B 注册 bedrock MCP server 到 .mcp.json (enabled)"
```

---

## Self-Review

**Spec 覆盖：**
- §3.2 8 tool → Task 2（4 tool）+ Task 3（4 tool）✅
- §5 双重构 → Task 1 ✅
- §6 错误处理（内联 try/except 抓 SystemExit）→ 每个 tool 体 ✅
- §3.1 _project_ok（workspace + db 存在）→ Task 2 Step3 + Task 4 测试 ✅
- §8 三层测试 → Task 1/2/3（层1）+ Task 4（层2）+ Task 1（层3）✅
- §10 验收 → Task 5 ✅

**抗博弈不变量贯穿：**
- tool 不崩 server（内联 try/except）→ test_tool_catches_exception_no_crash + test_unknown_global_number_returns_structured_error
- export 不暴露 out（path traversal）→ test_export_project_out_not_exposed
- project workspace 约束 → test_project_path_traversal_rejected
- 不创建空 db → test_missing_db_returns_structured_error
- run_l2 精简返回真实字段 → test_run_l2_check_returns_compact
- 双重构 DRY（CLI 行为不变）→ test_get_review_flag_cli_has_flag_output

**类型一致性：** chapter_id_by_global / compute_has_flag / _project_ok / json_error / export_project / diagnose / show_review_report / list_volumes / diff_drift / run_l2_check / get_chapter_flag / list_chapters——各 task 引用名一致。

**已知风险点：**
- Task 1 Step5：`_chapter_id` 保留薄包装委托 `chapter_id_by_global`（最小改动），所有 `cid = _chapter_id(conn, args.chapter)` 调用点不动。
- Task 4 `test_project_path_traversal_rejected`：依赖 `_project_ok` fallback `os.getcwd()`=workspace。若测试 cwd 非 D:\novel_test 会误判——可选 monkeypatch 设 NOVEL_WORKSPACE 锁定。
- FastMCP `@mcp.tool()` 对带 try/except 的函数生成 schema：依赖 type hint（dict/str/list）+ docstring，内联 try/except 不影响签名——Task 5 冒烟会验证 tool 注册成功。
