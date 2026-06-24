"""endpoint_repo 测试(全局 ~/.bedrock/global.db)。用 BEDROCK_GLOBAL_CONFIG 指向 temp db。"""
import json
from src.bedrock.runner import endpoint_repo


def _use_temp(monkeypatch, tmp_path):
    monkeypatch.setenv("BEDROCK_GLOBAL_CONFIG", str(tmp_path / "global.db"))


def test_empty(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    assert endpoint_repo.list_endpoints() == []


def test_upsert_and_get(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1", provider="anthropic", base_url="https://x",
                                   api_key="sk-secret1234", models=["m1", "m2"])
    g = endpoint_repo.get_endpoint("p1")
    assert g["provider"] == "anthropic"
    assert g["base_url"] == "https://x"
    assert g["api_key"] == "sk-secret1234"   # mask=False 含真值
    assert g["models"] == ["m1", "m2"]


def test_list_masks_key(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1", api_key="sk-secret1234", models=["m"])
    items = endpoint_repo.list_endpoints(mask=True)
    assert items[0]["api_key"] == ""           # 不回全文
    assert items[0]["api_key_set"] is True
    assert items[0]["api_key_tail"] == "1234"


def test_upsert_by_name_reuses_row(monkeypatch, tmp_path):
    """同名 upsert = 更新,不新增行。api_key None=保留。"""
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1", api_key="sk-1", base_url="https://a", models=["m1"])
    endpoint_repo.upsert_endpoint("p1", base_url="https://b")   # api_key/models None=保留
    g = endpoint_repo.get_endpoint("p1")
    assert g["api_key"] == "sk-1"     # 保留
    assert g["base_url"] == "https://b"
    assert g["models"] == ["m1"]      # 保留
    assert len(endpoint_repo.list_endpoints()) == 1   # 仍一行


def test_upsert_clear_key_with_empty_string(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1", api_key="sk-1")
    endpoint_repo.upsert_endpoint("p1", api_key="")   # 空串=清空
    g = endpoint_repo.get_endpoint("p1")
    assert g["api_key"] == ""


def test_delete(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1")
    assert endpoint_repo.delete_endpoint("p1") is True
    assert endpoint_repo.delete_endpoint("p1") is False   # 再删=不存在
    assert endpoint_repo.get_endpoint("p1") is None


def test_get_unknown_returns_none(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    assert endpoint_repo.get_endpoint("nope") is None


def test_name_unique_constraint(monkeypatch, tmp_path):
    """name 唯一:同名 insert 走 upsert 不重复(由 upsert 保证);直接插重名会抛。"""
    _use_temp(monkeypatch, tmp_path)
    endpoint_repo.upsert_endpoint("p1")
    endpoint_repo.upsert_endpoint("p1")   # 幂等,不抛
    assert len(endpoint_repo.list_endpoints()) == 1
