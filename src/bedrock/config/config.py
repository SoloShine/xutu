# src/bedrock/config/config.py
"""配置文件机制：项目级可变配置，覆盖默认常量。stdlib json（无 yaml 依赖）。"""
import json
from pathlib import Path

CONFIG_FILENAME = "bedrock_config.json"


def init_default_config(project_dir):
    """创建默认配置文件（若不存在）。"""
    project_dir = Path(project_dir)
    cfg_path = project_dir / CONFIG_FILENAME
    if cfg_path.exists():
        return
    default = {
        "volume_type_overrides": {},
        "style_thresholds": {"notXisY_max": 5, "dashes_per_k_max": 3, "periods_per_k_range": [15, 25]},
    }
    cfg_path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config(project_dir):
    """读配置文件覆盖默认。文件不存在则返回默认。"""
    project_dir = Path(project_dir)
    cfg_path = project_dir / CONFIG_FILENAME
    default = {
        "volume_type_overrides": {},
        "style_thresholds": {"notXisY_max": 5, "dashes_per_k_max": 3, "periods_per_k_range": [15, 25]},
    }
    if not cfg_path.exists():
        return default
    loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
    for k, v in loaded.items():
        default[k] = v
    return default
