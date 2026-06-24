# src/bedrock/runner/llm.py
"""两层 LLM 解析 + 默认回退:

  作品级绑定(workflow_config.models[process]={endpoint,model})  ← 仅填写时覆盖
    ↓ 未绑
  全局默认缺省(llm_default: endpoint+model)                    ← 回退
    ↓ 未设
  LLMNotBoundError

→ 全局端点(~/.bedrock/global.db llm_endpoint:name/provider/base_url/api_key)→ 构造模型。
分离"有哪些 LLM"(全局目录)、"默认用哪个"(全局默认)、"每个流程用哪个"(作品绑定覆盖)。
"""
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .endpoint_repo import get_endpoint
from .default_repo import get_default


class LLMNotBoundError(RuntimeError):
    """流程既无作品绑定、又无全局默认(endpoint 为空)。runner 应明确提示作者去配置面板。"""


def _binding_for(workflow_models: dict, process: str):
    """取 process 的绑定 {endpoint, model}。兼容旧格式(纯字符串 model)与 None。"""
    workflow_models = workflow_models or {}
    b = workflow_models.get(process)
    if isinstance(b, dict):
        return b.get("endpoint"), b.get("model")
    if isinstance(b, str) and b:           # 旧格式:纯 model 串(无 endpoint)→ 视为 model,endpoint 空
        return None, b
    return None, None


def get_writer_model(workflow_config, process: str = "writer") -> BaseChatModel:
    """构造 process 的 LLM。解析顺序:作品绑定(覆盖)→ 全局默认(回退)→ 全局端点 → init_chat_model。

    workflow_config:get_workflow_config() 的结果(含 models)。
    作品绑定填了 endpoint → 用绑定(整体覆盖,默认不介入)。
    作品绑定未填 endpoint → 用全局默认(endpoint+model)。
    两者皆无 → LLMNotBoundError。
    端点不在全局目录 → LLMNotBoundError。
    """
    workflow_models = workflow_config.get("models") if isinstance(workflow_config, dict) else workflow_config
    endpoint_name, model_id = _binding_for(workflow_models, process)

    if not endpoint_name:
        # 作品未绑 → 回退全局默认缺省
        d = get_default()
        if d and d.get("endpoint_name"):
            endpoint_name = d["endpoint_name"]
            if not model_id:
                model_id = d.get("model")
        if not endpoint_name:
            raise LLMNotBoundError(
                f"流程「{process}」既无作品绑定、又未设全局默认模型。"
                f"请在「LLM 端点」面板设默认模型,或在「工作流配置」为该流程选端点+模型。")

    endpoint = get_endpoint(endpoint_name, mask=False)
    if endpoint is None:
        raise LLMNotBoundError(
            f"端点「{endpoint_name}」不在全局目录。请在「LLM 端点」面板添加,或重选。")

    # model:已解析值 → 端点 models[0] 兜底
    if not model_id:
        models = endpoint.get("models") or []
        if not models:
            raise LLMNotBoundError(f"端点「{endpoint_name}」未配任何模型,流程「{process}」无法选。")
        model_id = models[0]

    provider = endpoint.get("provider") or "anthropic"
    kwargs = {}
    if endpoint.get("base_url"):
        kwargs["base_url"] = endpoint["base_url"]   # 第三方/代理端点
    if endpoint.get("api_key"):
        kwargs["api_key"] = endpoint["api_key"]
    return init_chat_model(model_id, model_provider=provider, **kwargs)
