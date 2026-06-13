import subprocess
import json
import shutil
import time
import sys

# Windows GBK 控制台兼容
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def call_llm(prompt: str, model: str = "sonnet",
             agent_id: str = None, tick: int = None,
             event_store=None, response_schema: dict = None):
    """通过 claude.cmd subprocess 调 LLM。

    response_schema 给定时：用 --json-schema constrained decoding，返回 structured_output（dict）。
    不给时：返回 result（str），保持 MVP1 行为。
    """
    claude_cmd = shutil.which("claude") or "claude"
    t0 = time.time()
    try:
        cmd = [claude_cmd, "-p", "--bare", "--output-format", "json", "--model", model]
        if response_schema is not None:
            cmd += ["--json-schema", json.dumps(response_schema, ensure_ascii=False)]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8")
        duration_ms = (time.time() - t0) * 1000
        parsed = json.loads(r.stdout)
        if response_schema is not None:
            output = parsed.get("structured_output", {})
        else:
            output = parsed.get("result", "")
        usage = parsed.get("usage", {})
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_{int(duration_ms)}",
                tick=tick if tick is not None else 0, event_type="call", agent_id=agent_id,
                payload={"prompt": prompt, "output": output, "duration_ms": duration_ms,
                         "tokens": usage, "model": model, "status": "ok",
                         "schema": bool(response_schema)}))
        return output
    except Exception as e:
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_err",
                tick=tick if tick is not None else 0, event_type="call", agent_id=agent_id,
                payload={"status": "error", "error": str(e), "model": model}))
        raise