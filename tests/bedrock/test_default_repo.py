"""default_repo 测试(全局 ~/.bedrock/global.db llm_default 单行)。用 BEDROCK_GLOBAL_CONFIG 指向 temp db。"""
from src.bedrock.runner import default_repo


def _use_temp(monkeypatch, tmp_path):
    monkeypatch.setenv("BEDROCK_GLOBAL_CONFIG", str(tmp_path / "global.db"))


def test_empty(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    assert default_repo.get_default() is None


def test_set_and_get(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    d = default_repo.set_default("GLM", "glm-5.2")
    assert d == {"endpoint_name": "GLM", "model": "glm-5.2"}
    assert default_repo.get_default() == {"endpoint_name": "GLM", "model": "glm-5.2"}


def test_set_overwrites(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    default_repo.set_default("GLM", "glm-5.2")
    default_repo.set_default("Claude", "claude-sonnet-4-6")
    assert default_repo.get_default() == {"endpoint_name": "Claude", "model": "claude-sonnet-4-6"}


def test_set_empty_endpoint_clears(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    default_repo.set_default("GLM", "glm-5.2")
    assert default_repo.set_default("", "") is None
    assert default_repo.get_default() is None


def test_clear(monkeypatch, tmp_path):
    _use_temp(monkeypatch, tmp_path)
    default_repo.set_default("GLM", "glm-5.2")
    default_repo.clear_default()
    assert default_repo.get_default() is None
    # clear 幂等(行不存在也能跑)
    default_repo.clear_default()
    assert default_repo.get_default() is None


def test_single_row_only(monkeypatch, tmp_path):
    """单行约束(id=1):多次 set 不新增行。"""
    _use_temp(monkeypatch, tmp_path)
    default_repo.set_default("A", "a1")
    default_repo.set_default("B", "b1")
    default_repo.set_default("C", "c1")
    from src.bedrock.runner.global_db import get_global_conn
    conn = get_global_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM llm_default").fetchone()
    conn.close()
    assert n["n"] == 1
