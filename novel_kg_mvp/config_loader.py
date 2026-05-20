"""
两级配置加载器：全局 config.yaml → 项目 project.yaml → 代码 DEFAULTS。

用法：
    from config_loader import config_loader
    cfg = config_loader.load("my_project")
    val = config_loader.get("my_project", "writing", "prev_text_chars", default=500)
"""

import os
import yaml
from typing import Any


# 所有可配置参数的默认值（=当前硬编码值）
DEFAULTS = {
    "writing": {
        "prev_text_chars": 500,
        "min_words": 2500,
        "max_words": 3500,
        "min_words_per_scene": 600,
    },
    "extraction": {
        "target_events": "5-8",
        "max_events": 10,
        "min_events": 3,
        "gap_keywords": ["尝到", "味道", "活在当下", "觉醒"],
    },
    "world_building": {
        "default_chapters": 6,
        "characters": "3-5",
        "locations": "3-5",
        "style_guides": "6-8",
        "time_periods": "2-3",
    },
    "derivation": {
        "scenes_per_arc": "3-5",
        "main_threads": "2-3",
        "nonlinear_ratio": 4,
        "lookback": 3,
    },
    "pacing": {
        "min_shared": 2,
        "flat_threshold": 4,
        "intense_diff": 5,
    },
    "structure": {
        "intercut_min": 2,
        "flashback_min": 1,
        "parallel_min": 2,
    },
    "suspense": {
        "budget_base": 8,
        "budget_multiplier": 1.5,
        "staleness_threshold": 3,
    },
    "validation": {
        "forbidden_patterns": [],
    },
    "collaboration": {
        "review_checkpoint": False,
        "outline_compliance": True,
        "auto_revise_outline": False,
        "semantic_check": True,
    },
}

_HERE = os.path.dirname(os.path.abspath(__file__))


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class _ConfigLoader:
    def __init__(self):
        self._cache: dict = {}

    def load(self, project: str = None) -> dict:
        if project in self._cache:
            return self._cache[project]

        config = {section: values.copy() for section, values in DEFAULTS.items()}

        # Layer 1: 全局 config.yaml
        global_path = os.path.join(_HERE, "config.yaml")
        if os.path.exists(global_path):
            with open(global_path, "r", encoding="utf-8") as f:
                global_cfg = yaml.safe_load(f) or {}
            if "novel" in global_cfg:
                config = _deep_merge(config, global_cfg["novel"])

        # Layer 2: 项目 project.yaml
        if project:
            project_path = os.path.join(_HERE, "projects", project, "project.yaml")
            if os.path.exists(project_path):
                with open(project_path, "r", encoding="utf-8") as f:
                    project_cfg = yaml.safe_load(f) or {}
                if "novel" in project_cfg:
                    config = _deep_merge(config, project_cfg["novel"])

        self._cache[project] = config
        return config

    def get(self, project: str, *path: str, default=None) -> Any:
        cfg = self.load(project)
        node = cfg
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    def clear_cache(self):
        self._cache.clear()


config_loader = _ConfigLoader()
