# tests/bedrock/test_config.py
from src.bedrock.config.volume_type_matrix import get_matrix, VOLUME_TYPE_MATRIX
from src.bedrock.config.config import load_config, init_default_config


def test_volume_type_matrix_has_all_types():
    for vt in ("opening", "advancing", "climax", "epilogue", "multi-pov"):
        m = get_matrix(vt)
        assert "may_plant_per_chapter" in m
        assert "mature_decline_floor" in m
        assert "pruning_quota" in m


def test_load_config_returns_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg["volume_type_overrides"] == {}


def test_init_and_load_config_with_override(tmp_path):
    init_default_config(tmp_path)
    assert (tmp_path / "bedrock_config.json").exists()
    import json
    (tmp_path / "bedrock_config.json").write_text(
        json.dumps({"volume_type_overrides": {"opening": {"pruning_quota": 1}}},
                   ensure_ascii=False), encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg["volume_type_overrides"]["opening"]["pruning_quota"] == 1
