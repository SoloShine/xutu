# tests/bedrock/test_telemetry.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.telemetry import (
    write_chapter_metrics, get_chapter_metrics,
    record_agent_invocation, record_llm_call, get_chapter_runtime,
    save_style_template,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed_chapter(conn, gnum=1):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    return create_chapter(conn, volume_id=vid, global_number=gnum, title="t")


def test_chapter_metrics_always_system_recomputed(tmp_project):
    conn = get_connection(tmp_project)
    cid = _seed_chapter(conn)
    write_chapter_metrics(conn, chapter_id=cid, word_count=4463,
                          grep_metrics={"notXisY": 2, "dash": 1, "period": 22},
                          threads_consumed=3, consumption_balance=1.5,
                          beat_yield_rate=1.0)
    m = get_chapter_metrics(conn, cid)
    assert m["source"] == "system_recomputed"
    assert m["word_count"] == 4463
    conn.close()


def test_chapter_runtime_records_blackwall_and_llm(tmp_project):
    conn = get_connection(tmp_project)
    cid = _seed_chapter(conn)
    rid = record_agent_invocation(conn, chapter_id=cid, agent_type="chapter_writer",
                                  black_wall_ms=300000)
    record_llm_call(conn, runtime_id=rid, phase="writing", model="claude-opus",
                    prompt_tokens=20000, completion_tokens=8000, duration_ms=295000)
    rt = get_chapter_runtime(conn, cid)
    assert rt["total_black_wall_ms"] == 300000
    assert rt["llm_tokens"] == 28000
    conn.close()


def test_style_template_roundtrip(tmp_project):
    conn = get_connection(tmp_project)
    sid = save_style_template(conn, fingerprint={"sentence_length_mean": 18.5},
                              sample_chapters=[1, 2, 3])
    assert sid is not None
    conn.close()
