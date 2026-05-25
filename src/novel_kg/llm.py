"""
LLM 调用模块 — OpenAI 兼容格式
支持 OpenAI / DeepSeek / Ollama / vLLM / 智谱 等兼容服务
API Key 优先从环境变量读取（api_key_env），其次用配置文件中的 api_key
"""

import sys
import json
import os
import time
import yaml
from openai import OpenAI


# V25 Telemetry: 上一次 LLM 调用的 token usage（供遥测模块读取）
_last_usage: dict = {}

def load_llm_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("LLM", {})


def get_api_key(cfg):
    """优先从环境变量读取，其次用配置文件中的直接值"""
    env_var = cfg.get("api_key_env")
    if env_var:
        key = os.environ.get(env_var)
        if key:
            return key
        raise ValueError(f"环境变量 {env_var} 未设置。请先 export {env_var}=your-key")
    direct_key = cfg.get("api_key", "")
    if direct_key:
        return direct_key
    raise ValueError("未配置 API Key。请在 config.yaml 中设置 api_key_env 或 api_key")


def get_client():
    cfg = load_llm_config()
    api_key = get_api_key(cfg)
    return OpenAI(
        base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        api_key=api_key,
    )


class _ProgressSpinner:
    """JSON模式下的进度指示器"""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label="处理中"):
        self.label = label
        self.start = None
        self.frame_idx = 0

    def tick(self):
        if self.start is None:
            self.start = time.time()
        elapsed = int(time.time() - self.start)
        frame = self.FRAMES[self.frame_idx % len(self.FRAMES)]
        self.frame_idx += 1
        sys.stderr.write(f"\r  {frame} {self.label}... {elapsed}s")
        sys.stderr.flush()

    def done(self, suffix=""):
        elapsed = int(time.time() - self.start) if self.start else 0
        sys.stderr.write(f"\r  ✓ {self.label}完成 ({elapsed}s) {suffix}\n")
        sys.stderr.flush()


def call_llm(prompt, system="你是一个专业的文学结构化分析助手。",
             json_mode=False, stream=False, stream_label=""):
    """调用LLM，返回文本或JSON

    stream=True 时逐token打印进度（仅适用于文本模式）。
    json_mode=True 时显示进度指示器。
    """
    cfg = load_llm_config()
    client = get_client()

    kwargs = {
        "model": cfg.get("model", "gpt-4o"),
        "max_tokens": cfg.get("max_tokens", 4096),
        "temperature": cfg.get("temperature", 0.7),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # 流式输出（文本生成）
    if stream and not json_mode:
        kwargs["stream"] = True
        response = client.chat.completions.create(**kwargs)
        chunks = []
        token_count = 0
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                text = delta.content
                chunks.append(text)
                sys.stdout.write(text)
                sys.stdout.flush()
                token_count += 1
                # 每100个token打印一次统计
                if token_count % 100 == 0:
                    sys.stderr.write(f"\n  [{token_count} tokens]\n")
                    sys.stderr.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()
        full_text = "".join(chunks).strip()
        return full_text

    # JSON模式：后台线程更新进度指示器
    if json_mode:
        import threading
        spinner = _ProgressSpinner(stream_label or "LLM处理")
        stop_event = threading.Event()

        def _spin():
            while not stop_event.is_set():
                spinner.tick()
                stop_event.wait(0.5)

        t = threading.Thread(target=_spin, daemon=True)
        t.start()

        try:
            response = client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content.strip()
            # V25: 捕获 token usage
            if hasattr(response, 'usage') and response.usage:
                _last_usage.update({
                    "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0) or 0,
                    "completion_tokens": getattr(response.usage, 'completion_tokens', 0) or 0,
                })
        finally:
            stop_event.set()
            t.join(timeout=1)
            spinner.done()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    # 普通同步调用
    response = client.chat.completions.create(**kwargs)
    # V25: 捕获 token usage
    if hasattr(response, 'usage') and response.usage:
        _last_usage.update({
            "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0) or 0,
            "completion_tokens": getattr(response.usage, 'completion_tokens', 0) or 0,
        })
    return response.choices[0].message.content.strip()


# ========== 预设调用 ==========

def extract_from_text(prompt):
    """提取结构化数据（返回JSON）"""
    return call_llm(prompt, json_mode=True, stream_label="提取结构化数据")


def derive_arc(prompt):
    """推演章节弧线（返回JSON）"""
    return call_llm(prompt, json_mode=True, stream_label="推演章节弧线")


def generate_chapter(prompt):
    """续写章节（流式输出文本）"""
    return call_llm(
        prompt,
        system="你是一位严肃文学作家。根据提供的结构化上下文续写小说章节。",
        stream=True,
    )


def generate_world(direction, project=None):
    """生成世界观设定（返回JSON）"""
    from .prompts import WORLD_BUILD_PROMPT
    from .config_loader import config_loader
    cfg = config_loader.load(project)
    wb_cfg = cfg.get("world_building", {})
    prompt = WORLD_BUILD_PROMPT.format(
        direction=direction,
        default_chapters=wb_cfg.get("default_chapters", 6),
        characters_range=wb_cfg.get("characters", "3-5"),
        locations_range=wb_cfg.get("locations", "3-5"),
        style_guides_range=wb_cfg.get("style_guides", "6-8"),
        time_periods_range=wb_cfg.get("time_periods", "2-3"),
    )
    return call_llm(prompt, json_mode=True, stream_label="生成世界观")


def generate_outline(world_setup, total_chapters=6, project=None):
    """生成全局大纲（返回JSON）"""
    from .prompts import OUTLINE_GENERATION_PROMPT
    from .config_loader import config_loader
    cfg = config_loader.load(project)
    derivation_cfg = cfg.get("derivation", {})
    prompt = OUTLINE_GENERATION_PROMPT.format(
        world_setup=json.dumps(world_setup, ensure_ascii=False, indent=2),
        total_chapters=total_chapters,
        main_threads=derivation_cfg.get("main_threads", "2-3"),
        nonlinear_ratio=derivation_cfg.get("nonlinear_ratio", 4),
    )
    return call_llm(prompt, json_mode=True, stream_label="生成大纲")


def prequery_plan(prompt):
    """预查询阶段1：轻量规划调用"""
    return call_llm(prompt, json_mode=True, stream_label="预查询规划")
