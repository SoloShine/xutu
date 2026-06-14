# tests/bedrock/test_runtime_collect.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.runtime_collect import write_runtime
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return vid, cid


def test_write_runtime_creates_row_and_aggregates(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    invocations = [
        {"agent_type": "ChapterWriter", "black_wall_ms": 5000, "start_ts": None, "end_ts": None},
        {"agent_type": "Edit", "black_wall_ms": 3000, "start_ts": None, "end_ts": None},
    ]
    llm_calls = [
        {"phase": "write", "model": "opus", "prompt_tokens": 1000, "completion_tokens": 500, "duration_ms": 4000},
    ]
    write_runtime(conn, cid, invocations, llm_calls, editing_rounds=1)
    rt = conn.execute("SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    assert rt["editing_rounds"] == 1
    assert rt["total_black_wall_ms"] == 8000   # 5000 + 3000
    assert rt["llm_tokens"] == 1500             # 1000 + 500
    assert rt["llm_call_count"] == 1
    n_inv = conn.execute("SELECT COUNT(*) AS n FROM agent_invocation WHERE runtime_id=?",
                         (rt["id"],)).fetchone()["n"]
    assert n_inv == 2
    conn.close()


def test_write_runtime_empty_inputs(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    write_runtime(conn, cid, [], [], editing_rounds=0)
    rt = conn.execute("SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    assert rt["editing_rounds"] == 0
    assert rt["total_black_wall_ms"] == 0
    conn.close()
