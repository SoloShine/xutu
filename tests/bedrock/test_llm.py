"""llm.py 两层 + 默认回退解析测试。mock get_endpoint/get_default/init_chat_model,验解析顺序。"""
import pytest
from src.bedrock.runner import llm as llm_mod


def _ep(name="GLM", models=None, provider="anthropic", base_url="https://x", api_key="sk-1"):
    return {"name": name, "provider": provider, "base_url": base_url,
            "api_key": api_key, "models": models or ["glm-5.2", "glm-5.1"]}


@pytest.fixture
def captured(monkeypatch):
    cap = {"model": None, "kwargs": None}

    def fake_init(model_id, *, model_provider=None, **kwargs):
        cap["model"] = model_id
        cap["provider"] = model_provider
        cap["kwargs"] = kwargs
        return f"<MockModel {model_id}>"

    monkeypatch.setattr(llm_mod, "init_chat_model", fake_init)
    return cap


def test_binding_overrides_default(monkeypatch, captured):
    # workflow 绑了 → 用绑定,默认不被咨询
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "OTHER", "model": "other-m"})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name, ["a", "b"]))
    cfg = {"models": {"writer": {"endpoint": "GLM", "model": "glm-5.2"}}}
    llm_mod.get_writer_model(cfg, "writer")
    assert captured["model"] == "glm-5.2"
    assert captured["provider"] == "anthropic"
    assert captured["kwargs"]["base_url"] == "https://x"


def test_unbound_falls_back_to_default(monkeypatch, captured):
    # workflow 空 → 回退默认(endpoint+model)
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "GLM", "model": "glm-5.2"})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name))
    llm_mod.get_writer_model({"models": {}}, "editor")
    assert captured["model"] == "glm-5.2"


def test_neither_binding_nor_default_raises(monkeypatch, captured):
    monkeypatch.setattr(llm_mod, "get_default", lambda: None)
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name))
    with pytest.raises(llm_mod.LLMNotBoundError):
        llm_mod.get_writer_model({"models": {}}, "writer")


def test_default_without_model_uses_endpoint_first(monkeypatch, captured):
    # 默认 endpoint 有、model 空 → 端点 models[0]
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "GLM", "model": ""})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name, ["glm-5.2", "glm-5.1"]))
    llm_mod.get_writer_model({"models": {}}, "writer")
    assert captured["model"] == "glm-5.2"   # models[0]


def test_default_endpoint_missing_from_catalog_raises(monkeypatch, captured):
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "Ghost", "model": "m"})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: None)
    with pytest.raises(llm_mod.LLMNotBoundError):
        llm_mod.get_writer_model({"models": {}}, "writer")


def test_binding_endpoint_missing_raises(monkeypatch, captured):
    monkeypatch.setattr(llm_mod, "get_default", lambda: None)
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: None)
    cfg = {"models": {"writer": {"endpoint": "Ghost", "model": "m"}}}
    with pytest.raises(llm_mod.LLMNotBoundError):
        llm_mod.get_writer_model(cfg, "writer")


def test_empty_default_string_treated_as_unset(monkeypatch, captured):
    # get_default 返 endpoint_name="" → 视为未设 → 报错
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "", "model": ""})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name))
    with pytest.raises(llm_mod.LLMNotBoundError):
        llm_mod.get_writer_model({"models": {}}, "writer")


def test_call_llm_captures_tokens_and_identity(monkeypatch):
    """call_llm resolve+invoke+捕 token/延迟/endpoint/model,返回遥测 dict。"""
    class FakeResp:
        content = "hello"
        usage_metadata = {"input_tokens": 13, "output_tokens": 93, "total_tokens": 106}
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "GLM", "model": "glm-5.2"})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name))
    monkeypatch.setattr(llm_mod, "init_chat_model", lambda *a, **k: type("M", (), {"invoke": lambda self, p: FakeResp()})())
    r = llm_mod.call_llm({"models": {}}, "writer", "prompt")
    assert r["content"] == "hello"
    assert r["tokens_in"] == 13 and r["tokens_out"] == 93
    assert r["endpoint"] == "GLM" and r["model"] == "glm-5.2"
    assert isinstance(r["latency_ms"], int) and r["latency_ms"] >= 0


def test_call_llm_missing_usage_yields_none(monkeypatch):
    """响应无 usage_metadata → tokens_* 为 None(不崩)。"""
    class FakeResp:
        content = "hi"
        usage_metadata = None
    monkeypatch.setattr(llm_mod, "get_default", lambda: {"endpoint_name": "GLM", "model": "glm-5.2"})
    monkeypatch.setattr(llm_mod, "get_endpoint", lambda name, mask=False: _ep(name))
    monkeypatch.setattr(llm_mod, "init_chat_model", lambda *a, **k: type("M", (), {"invoke": lambda self, p: FakeResp()})())
    r = llm_mod.call_llm({"models": {}}, "writer", "p")
    assert r["content"] == "hi"
    assert r["tokens_in"] is None and r["tokens_out"] is None
