# src/bedrock/runner/llm.py
"""两层 LLM 解析 + 默认回退 + token 遥测:

  作品级绑定(workflow_config.models[process]={endpoint,model})  ← 仅填写时覆盖
    ↓ 未绑
  全局默认缺省(llm_default: endpoint+model)                    ← 回退
    ↓ 未设
  LLMNotBoundError

→ 全局端点(~/.bedrock/global.db llm_endpoint)→ 构造模型 → invoke。
节点统一走 call_llm()(resolve+invoke+捕 token/延迟/endpoint/model),每次调用 emit llm_call event。
"""
import time
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .endpoint_repo import get_endpoint
from .default_repo import get_default


class LLMNotBoundError(RuntimeError):
    """流程既无作品绑定、又无全局默认(endpoint 为空)。runner 应明确提示作者去配置面板。"""


def _binding_for(workflow_models: dict, process: str):
    """取 process 的作品绑定 {endpoint, model}。兼容旧格式(纯字符串 model)与 None。"""
    workflow_models = workflow_models or {}
    b = workflow_models.get(process)
    if isinstance(b, dict):
        return b.get("endpoint"), b.get("model")
    if isinstance(b, str) and b:           # 旧格式:纯 model 串(无 endpoint)→ 视为 model,endpoint 空
        return None, b
    return None, None


def _resolve_endpoint_model(workflow_config, process: str):
    """解析 (endpoint_name, model_id)。顺序:作品绑定(覆盖)→ 全局默认(回退)。
    作品绑定填了 endpoint → 用绑定(整体覆盖);未填 → 全局默认;皆无 → LLMNotBoundError。"""
    workflow_models = workflow_config.get("models") if isinstance(workflow_config, dict) else workflow_config
    endpoint_name, model_id = _binding_for(workflow_models, process)
    if not endpoint_name:
        d = get_default()
        if d and d.get("endpoint_name"):
            endpoint_name = d["endpoint_name"]
            if not model_id:
                model_id = d.get("model")
        if not endpoint_name:
            raise LLMNotBoundError(
                f"流程「{process}」既无作品绑定、又未设全局默认模型。"
                f"请在「LLM 端点」面板设默认模型,或在「工作流配置」为该流程选端点+模型。")
    return endpoint_name, model_id


def _build_model(endpoint_name: str, model_id) -> BaseChatModel:
    """按 endpoint_name 取全局端点 → init_chat_model(base_url+api_key 来自端点)。"""
    endpoint = get_endpoint(endpoint_name, mask=False)
    if endpoint is None:
        raise LLMNotBoundError(
            f"端点「{endpoint_name}」不在全局目录。请在「LLM 端点」面板添加,或重选。")
    if not model_id:
        models = endpoint.get("models") or []
        if not models:
            raise LLMNotBoundError(f"端点「{endpoint_name}」未配任何模型,无法选。")
        model_id = models[0]
    provider = endpoint.get("provider") or "anthropic"
    kwargs = {}
    if endpoint.get("base_url"):
        kwargs["base_url"] = endpoint["base_url"]
    if endpoint.get("api_key"):
        kwargs["api_key"] = endpoint["api_key"]
    return init_chat_model(model_id, model_provider=provider, **kwargs), model_id


def get_writer_model(workflow_config, process: str = "writer") -> BaseChatModel:
    """[兼容] resolve + build,返回模型对象(不 invoke、不捕 token)。新代码用 call_llm。"""
    endpoint_name, model_id = _resolve_endpoint_model(workflow_config, process)
    model, _ = _build_model(endpoint_name, model_id)
    return model


def call_llm(workflow_config, process: str, prompt: str) -> dict:
    """resolve + invoke + 捕 token/延迟/endpoint/model。返回遥测 dict(供节点 emit llm_call event)。

    返回 {content, endpoint, model, tokens_in, tokens_out, latency_ms}。
    tokens_* 为 None 表示响应未带 usage_metadata。
    """
    endpoint_name, model_id = _resolve_endpoint_model(workflow_config, process)
    t0 = time.perf_counter()
    model, model_id = _build_model(endpoint_name, model_id)
    resp = model.invoke(prompt)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    content = resp.content if hasattr(resp, "content") else str(resp)
    usage = getattr(resp, "usage_metadata", None) or {}
    return {
        "content": content,
        "endpoint": endpoint_name,
        "model": model_id,
        "tokens_in": usage.get("input_tokens"),
        "tokens_out": usage.get("output_tokens"),
        "latency_ms": latency_ms,
    }
