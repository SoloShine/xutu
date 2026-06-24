import json
from src.bedrock.db.connection import get_connection
from src.bedrock.workflow.config_repo import (
    get_workflow_config, set_workflow_config, list_workflow_configs, get_defaults,
    _DEFAULT_CAPS, _DEFAULT_MODELS, _DEFAULT_PHASES, _DEFAULT_PROMPTS,
)


def test_no_row_returns_frozen_defaults(tmp_project):
    """无任何行 → 纯代码默认（冻结快照 = .js 现状）。"""
    conn = get_connection(tmp_project)
    cfg = get_workflow_config(conn)
    assert cfg["has_row"] is False
    assert cfg["scope"] is None
    assert cfg["caps"] == _DEFAULT_CAPS
    assert cfg["models"] == _DEFAULT_MODELS
    assert cfg["phases"] == _DEFAULT_PHASES
    assert cfg["prompts"] == _DEFAULT_PROMPTS
    # 冻结快照关键值（与 .js 现状一致）
    assert cfg["caps"]["writer"] == 3
    assert cfg["caps"]["editor"] == 5
    assert cfg["models"]["volume_review"] == {"endpoint": None, "model": None}   # 新格式:未配置
    assert cfg["phases"]["polish"] == "auto"
    conn.close()


def test_round_trip_work_scope(tmp_project):
    """set→get 一致（work scope）。"""
    conn = get_connection(tmp_project)
    rid = set_workflow_config(conn, "work", caps={"writer": 4})
    assert rid
    cfg = get_workflow_config(conn)
    assert cfg["has_row"] is True
    assert cfg["scope"] == "work"
    assert cfg["caps"]["writer"] == 4
    conn.close()


def test_upsert_does_not_overwrite_other_categories(tmp_project):
    """set models 不动 caps（upsert 只更非 None 类别）。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 7})
    set_workflow_config(conn, "work", models={"writer": {"endpoint": "p1", "model": "m1"}})
    cfg = get_workflow_config(conn)
    assert cfg["caps"]["writer"] == 7          # 保留
    assert cfg["models"]["writer"] == {"endpoint": "p1", "model": "m1"}  # 新写入(绑定格式)
    conn.close()


def test_deep_field_level_merge_within_category(tmp_project):
    """volume 改一个 cap，其余 cap 仍回退 work/默认（深度逐键 merge，非整类替换）。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 4})
    # 需要先建一个 volume（FK）。直接插 workflow_config volume 行即可（无 FK 约束）。
    set_workflow_config(conn, "volume", volume_id=1, caps={"editor": 9})
    # 卷级视角：writer 来自 work（4），editor 来自 volume（9），其余默认
    cfg = get_workflow_config(conn, volume_id=1)
    assert cfg["scope"] == "volume"
    assert cfg["caps"]["writer"] == 4   # work
    assert cfg["caps"]["editor"] == 9   # volume 覆盖
    assert cfg["caps"]["repair"] == _DEFAULT_CAPS["repair"]  # 默认
    conn.close()


def test_volume_overrides_work_same_key(tmp_project):
    """volume 的 writer 覆盖 work 的 writer（同键 volume 胜）。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 4})
    set_workflow_config(conn, "volume", volume_id=1, caps={"writer": 6})
    cfg = get_workflow_config(conn, volume_id=1)
    assert cfg["caps"]["writer"] == 6
    conn.close()


def test_work_scope_ignores_volume_overrides(tmp_project):
    """work 视角（不传 volume）不受 volume 行影响。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 4})
    set_workflow_config(conn, "volume", volume_id=1, caps={"writer": 6, "editor": 9})
    cfg = get_workflow_config(conn)  # 无 volume_id
    assert cfg["scope"] == "work"
    assert cfg["caps"]["writer"] == 4
    assert cfg["caps"]["editor"] == _DEFAULT_CAPS["editor"]  # 不被 volume 带入
    conn.close()


def test_none_value_does_not_override(tmp_project):
    """显式 None = 不覆盖（保留上层值），用于 merge 时跳过未设键。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", models={"writer": {"endpoint": "p1", "model": "m1"}})
    set_workflow_config(conn, "volume", volume_id=1, models={"writer": None, "editor": {"endpoint": "p2", "model": "m2"}})
    cfg = get_workflow_config(conn, volume_id=1)
    assert cfg["models"]["writer"] == {"endpoint": "p1", "model": "m1"}  # None 不覆盖,work 值生效
    assert cfg["models"]["editor"] == {"endpoint": "p2", "model": "m2"}
    conn.close()


def test_one_row_per_scope_volume(tmp_project):
    """同 scope+volume_id 多次 set 只一行（upsert，不插重复）。"""
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 1})
    set_workflow_config(conn, "work", caps={"writer": 2})
    set_workflow_config(conn, "work", caps={"writer": 3})
    rows = conn.execute("SELECT COUNT(*) AS n FROM workflow_config WHERE scope='work'").fetchone()
    assert rows["n"] == 1
    cfg = get_workflow_config(conn)
    assert cfg["caps"]["writer"] == 3  # 最后一次
    conn.close()


def test_list_workflow_configs(tmp_project):
    conn = get_connection(tmp_project)
    set_workflow_config(conn, "work", caps={"writer": 4})
    set_workflow_config(conn, "volume", volume_id=2, models={"editor": {"endpoint": "p2", "model": "m2"}})
    items = list_workflow_configs(conn)
    assert len(items) == 2
    by_scope = {(i["scope"], i["volume_id"]): i for i in items}
    assert by_scope[("work", None)]["caps"] == {"writer": 4}
    assert by_scope[("volume", 2)]["models"] == {"editor": {"endpoint": "p2", "model": "m2"}}
    conn.close()


def test_get_defaults_is_snapshot(tmp_project):
    """get_defaults 返回冻结快照深拷贝，改它不影响后续。"""
    conn = get_connection(tmp_project)
    d = get_defaults()
    assert d["caps"]["writer"] == 3
    d["caps"]["writer"] = 999  # 改副本
    assert get_defaults()["caps"]["writer"] == 3  # 原未受影响
    conn.close()


def test_volume_scope_requires_volume_id(tmp_project):
    """scope=volume 必须给 volume_id。"""
    conn = get_connection(tmp_project)
    try:
        set_workflow_config(conn, "volume", caps={"writer": 1})
        assert False, "应抛 ValueError"
    except ValueError:
        pass
    conn.close()


def test_migration_idempotent(tmp_project):
    """重复 apply_migrations 不报错、表不重建重复（CREATE IF NOT EXISTS）。"""
    from src.bedrock.db.migrate import apply_migrations
    apply_migrations(tmp_project)  # 第二次
    apply_migrations(tmp_project)  # 第三次
    conn = get_connection(tmp_project)
    cfg = get_workflow_config(conn)  # 仍可用
    assert cfg["caps"]["writer"] == 3
    n = conn.execute("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name='workflow_config'").fetchone()
    assert n["n"] == 1  # 表只一个
    conn.close()
