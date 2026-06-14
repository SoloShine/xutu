"""磐石 Bedrock MCP Server：把只读能力暴露给对话层（Claude Code）。复用 SP6-A 纯函数层。
8 tool 全部只读或仅 export。tool 体内联 try/except 专抓 SystemExit（FastMCP 已兜 Exception，
但 SystemExit 是 BaseException 子类穿透它杀进程；纯函数层大量 raise SystemExit）。
不暴露治理写入（mark-*/unlock-volume）——抗博弈。"""
import json
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.cli.reader_commands import (
    do_export, diagnose as diagnose_fn, show_review_report as show_fn,
    detect_drift, render_drift_report,
)
from src.bedrock.orchestration.review_flag import get_review_flag, compute_has_flag
from src.bedrock.orchestration.l2_pipeline import run_l2
from dataclasses import asdict

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


def _err(msg):
    """统一错误返回（dict，便于对话层/测试解析）。"""
    return {"error": msg}


# 别名：与 SP6-B plan 命名一致。
json_error = _err


@mcp.tool()
def export_project(project: str, scope: str, target: int = None,
                   fmt: str = "md", final: bool = False) -> dict:
    """导出正文成稿（paragraph→文件，单向）。scope=chapter/volume/book；
    chapter 的 target=global_number，volume 的 target=volume.id，book 无 target。
    返回 {path,content_hash,chapter_count}。"""
    try:
        err = _project_ok(project)
        if err:
            return _err(err)
        if scope in ("chapter", "volume") and target is None:
            return _err(f"scope={scope} 需 target")
        conn = _open_conn(project)
        try:
            if scope == "chapter":
                t = chapter_id_by_global(conn, target)
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
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def diagnose(project: str, scope: str, volume_id: int = None,
             with_l2: bool = False):
    """体检报告（聚合管线留痕旗+章节状态+跨卷欠债）。默认 flag-only（快）；
    with_l2=True 对卷内每章现场跑 run_l2 重算（慢，逐章 CPU），仅当需对当前正文做独立
    信任检查时开。scope=volume 需 volume_id(volume.id)；scope=book 全书。
    成功返回 markdown str；输入校验/异常返回 {"error": ...} dict。"""
    try:
        err = _project_ok(project)
        if err:
            return _err(err)
        if scope == "volume" and volume_id is None:
            return _err("scope=volume 需 volume_id")
        conn = _open_conn(project)
        try:
            sc = ("volume", volume_id) if scope == "volume" else ("book", None)
            return diagnose_fn(conn, project, sc, with_l2)
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def show_review_report(project: str, volume_id: int,
                       escalate_only: bool = False, plain: bool = False):
    """读 review_report_vol{volume_id}.md（SP5 生成的整卷回读报告）。
    escalate_only=True 只列需人工判决(escalate_human)项；plain=True 去 markdown 省token。
    成功返回 str；异常返回 {"error": ...} dict。"""
    try:
        err = _project_ok(project)   # 仍校验项目（报告文件在项目目录下）
        if err:
            return _err(err)
        return show_fn(project, volume_id, escalate_only, plain)   # 纯文件读，不开 conn
    except (SystemExit, Exception) as e:
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def list_volumes(project: str) -> list:
    """列出全部卷(id/number/name/起止章/类型)，按卷号升序。"""
    try:
        err = _project_ok(project)
        if err:
            return [_err(err)]
        conn = _open_conn(project)
        try:
            rows = conn.execute(
                "SELECT id, number, name, chapter_start, chapter_end, volume_type "
                "FROM volume ORDER BY number").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (SystemExit, Exception) as e:
        return [_err(f"{type(e).__name__}: {e}")]


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


if __name__ == "__main__":
    mcp.run()
