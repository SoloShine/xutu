# src/bedrock/orchestration/runtime_collect.py
"""黑墙遥测采集：建一个 chapter_runtime 聚合行 + 批量挂 agent_invocation/llm_call 子行。
编排层（Workflow JS）在子代理结束后从 SDK usage 汇报，传本函数落库。
【新逻辑，非封装 record_agent_invocation】——后者一行/agent 会破坏单章聚合。"""
from src.bedrock.repositories.telemetry import _create_runtime


def write_runtime(conn, chapter_id, invocations, llm_calls, editing_rounds):
    """invocations: [{agent_type, black_wall_ms, start_ts?, end_ts?}]
    llm_calls: [{phase, model, prompt_tokens, completion_tokens, duration_ms}]
    建 1 个 chapter_runtime 行（editing_rounds + 累加 total_black_wall_ms/llm_tokens/llm_call_count）
    + N agent_invocation 子行 + M llm_call 子行，全挂同一 runtime_id。"""
    total_bw = sum(inv.get("black_wall_ms", 0) for inv in invocations)
    total_tokens = sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in llm_calls)
    runtime_id = _create_runtime(conn, chapter_id, editing_rounds=editing_rounds)
    conn.execute(
        "UPDATE chapter_runtime SET total_black_wall_ms=?, tool_count=?, llm_tokens=?, llm_call_count=? "
        "WHERE id=?",
        (total_bw, len(invocations), total_tokens, len(llm_calls), runtime_id))
    for inv in invocations:
        conn.execute(
            "INSERT INTO agent_invocation(runtime_id,agent_type,start_ts,end_ts,black_wall_ms) "
            "VALUES(?,?,?,?,?)",
            (runtime_id, inv["agent_type"], inv.get("start_ts"), inv.get("end_ts"),
             inv.get("black_wall_ms", 0)))
    for c in llm_calls:
        conn.execute(
            "INSERT INTO llm_call(runtime_id,phase,model,prompt_tokens,completion_tokens,duration_ms) "
            "VALUES(?,?,?,?,?,?)",
            (runtime_id, c["phase"], c["model"], c.get("prompt_tokens", 0),
             c.get("completion_tokens", 0), c.get("duration_ms", 0)))
    conn.commit()
