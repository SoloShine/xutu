# src/bedrock/repositories/telemetry.py
import json


def write_chapter_metrics(conn, chapter_id, word_count=None, sentence_length_stats=None,
                          grep_metrics=None, sensory_density=None, dialogue_ratio=None,
                          threads_consumed=None, consumption_balance=None,
                          beat_yield_rate=None, declared=None):
    """authoritative 写入——source 永远 system_recomputed。declared 进 declared_json（advisory）。"""
    conn.execute(
        "INSERT OR REPLACE INTO chapter_metrics("
        "chapter_id,word_count,sentence_length_stats,grep_metrics,sensory_density,"
        "dialogue_ratio,threads_consumed,consumption_balance,beat_yield_rate,declared_json,source) "
        "VALUES(?,?,?,?,?,?,?,?,?,?, 'system_recomputed')",
        (chapter_id, word_count,
         json.dumps(sentence_length_stats or {}, ensure_ascii=False),
         json.dumps(grep_metrics or {}, ensure_ascii=False),
         sensory_density, dialogue_ratio, threads_consumed, consumption_balance,
         beat_yield_rate, json.dumps(declared or {}, ensure_ascii=False)))
    conn.commit()


def get_chapter_metrics(conn, chapter_id):
    return conn.execute("SELECT * FROM chapter_metrics WHERE chapter_id=?",
                        (chapter_id,)).fetchone()


def _create_runtime(conn, chapter_id, session_id=None, version=None, editing_rounds=0):
    cur = conn.execute(
        "INSERT INTO chapter_runtime(chapter_id,session_id,version,editing_rounds) "
        "VALUES(?,?,?,?)", (chapter_id, session_id, version, editing_rounds))
    conn.commit()
    return cur.lastrowid


def record_agent_invocation(conn, chapter_id, agent_type, black_wall_ms,
                            start_ts=None, end_ts=None, session_id=None, version=None):
    rid = _create_runtime(conn, chapter_id, session_id, version)
    conn.execute(
        "INSERT INTO agent_invocation(runtime_id,agent_type,start_ts,end_ts,black_wall_ms) "
        "VALUES(?,?,?,?,?)", (rid, agent_type, start_ts, end_ts, black_wall_ms))
    conn.execute(
        "UPDATE chapter_runtime SET total_black_wall_ms=total_black_wall_ms+? WHERE id=?",
        (black_wall_ms, rid))
    conn.commit()
    return rid


def record_llm_call(conn, runtime_id, phase, model, prompt_tokens, completion_tokens, duration_ms):
    conn.execute(
        "INSERT INTO llm_call(runtime_id,phase,model,prompt_tokens,completion_tokens,duration_ms) "
        "VALUES(?,?,?,?,?,?)", (runtime_id, phase, model, prompt_tokens, completion_tokens, duration_ms))
    conn.execute(
        "UPDATE chapter_runtime SET llm_tokens=llm_tokens+?, llm_call_count=llm_call_count+1 WHERE id=?",
        (prompt_tokens + completion_tokens, runtime_id))
    conn.commit()


def get_chapter_runtime(conn, chapter_id):
    return conn.execute(
        "SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
        (chapter_id,)).fetchone()


def save_style_template(conn, fingerprint, source_works=None, sample_chapters=None,
                        scope="work", volume_id=None):
    cur = conn.execute(
        "INSERT INTO style_template(source_works,sample_chapters,fingerprint,scope,volume_id) "
        "VALUES(?,?,?,?,?)",
        (json.dumps(source_works or [], ensure_ascii=False),
         json.dumps(sample_chapters or [], ensure_ascii=False),
         json.dumps(fingerprint, ensure_ascii=False),
         scope, volume_id))
    conn.commit()
    return cur.lastrowid
