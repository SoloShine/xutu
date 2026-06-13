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
             event_store=None) -> str:
    """通过 claude.cmd subprocess 调 LLM。所有调用统一入口（telemetry 可选）。

    --bare: 跳过项目 CLAUDE.md/hooks（纯 LLM，避免污染）
    --output-format json: 取结构化 result + usage
    """
    t0 = time.time()
    try:
        # PATH 解析（无硬编码平台路径）。subprocess 在 Windows 上不会自动
        # 搜索 PATHEXT（claude.CMD），故用 shutil.which 显式解析。
        claude_cmd = shutil.which("claude") or "claude"

        r = subprocess.run(
            [claude_cmd, "-p", "--bare", "--output-format", "json", "--model", model],
            input=prompt, capture_output=True, text=True, encoding="utf-8",
        )
        duration_ms = (time.time() - t0) * 1000
        parsed = json.loads(r.stdout)
        output = parsed.get("result", "")
        usage = parsed.get("usage", {})

        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_{int(duration_ms)}",
                tick=tick if tick is not None else 0,
                event_type="call",
                agent_id=agent_id,
                payload={
                    "prompt": prompt, "output": output,
                    "duration_ms": duration_ms, "tokens": usage,
                    "model": model, "status": "ok",
                },
            ))
        return output
    except Exception as e:
        if event_store is not None:
            from .schemas import Event
            event_store.append(Event(
                event_id=f"call_{agent_id}_t{tick}_err",
                tick=tick if tick is not None else 0,
                event_type="call", agent_id=agent_id,
                payload={"status": "error", "error": str(e), "model": model},
            ))
        raise