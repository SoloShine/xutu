# 磐石 Bedrock SP2 — 防漂移校验库 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SP1 数据骨架上建防漂移校验库（beat 兑现校验/卷大纲 amendment/跨卷锚点门禁/override 入口）+ 配置基础设施。纯 Python，无 agent 编排/LLM。

**Architecture:** `src/bedrock/checks/` 校验函数 + `src/bedrock/config/` 配置基础设施 + 扩展 repositories/。基于 SP1 schema（无新表）。校验函数输入 DB 状态输出 violations，不更新状态（SP4 编排负责状态迁移）。

**Tech Stack:** Python 3.10+ stdlib（sqlite3/json/dataclasses/pathlib），pytest。

**前置:** SP1 已完成（`src/bedrock/` 38 表 40 测试，分支 `bedrock-sp1`）。spec: `docs/superpowers/specs/2026-06-14-bedrock-sp2-anti-drift-design.md`。

---

## 文件结构

```
src/bedrock/
├── checks/                      # SP2 新增
│   ├── __init__.py
│   ├── beat_fulfillment.py      # Task 3: beat 兑现校验
│   └── cross_volume.py          # Task 4: 跨卷锚点校验
├── config/                      # SP2 新增
│   ├── __init__.py
│   ├── volume_type_matrix.py    # Task 1: 静态常量表
│   └── config.py                # Task 1: 配置文件机制
├── repositories/
│   ├── outline.py               # Task 2: 扩展 unlock/relock/update_beat_contract/get_beat_contract
│   └── plot_tree.py             # Task 5: 扩展 mark_override
└── ...（SP1 已有）
tests/bedrock/
├── test_config.py               # Task 1
├── test_amendment.py            # Task 2
├── test_beat_fulfillment.py     # Task 3
├── test_cross_volume.py         # Task 4
└── test_override.py             # Task 5
```

**Task 顺序按依赖**（非 spec §编号）：配置基础设施（1）→ amendment+beat契约结构（2）→ beat兑现校验（3，依赖2的 beat_contracts）→ 跨卷锚点（4）→ override（5）。

---

## Task 1: 配置基础设施（卷类型矩阵 + 配置文件机制）

**Files:**
- Create: `src/bedrock/config/__init__.py`（空）
- Create: `src/bedrock/config/volume_type_matrix.py`
- Create: `src/bedrock/config/config.py`
- Test: `tests/bedrock/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
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
    # 手动写一个覆盖
    import json
    (tmp_path / "bedrock_config.json").write_text(
        json.dumps({"volume_type_overrides": {"opening": {"pruning_quota": 1}}},
                   ensure_ascii=False), encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg["volume_type_overrides"]["opening"]["pruning_quota"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_config.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `config/volume_type_matrix.py`**

```python
# src/bedrock/config/volume_type_matrix.py
"""卷类型矩阵静态常量表。SP2 建基础设施，配额查询逻辑在 SP5。"""

VOLUME_TYPE_MATRIX = {
    "opening": {
        "may_plant_per_chapter": (3, 4),
        "mature_decline_floor": 0,
        "pruning_quota": 0,
        "net_balance_range": (5, 10),
    },
    "advancing": {
        "may_plant_per_chapter": (1, 2),
        "mature_decline_floor": "floor(N/3)",
        "pruning_quota": 10,
        "net_balance_range": (-2, 2),
    },
    "climax": {
        "may_plant_per_chapter": (0, 1),
        "mature_decline_floor": "floor(N/2)",
        "pruning_quota": 15,
        "net_balance_range": (-99, -5),
    },
    "epilogue": {
        "may_plant_per_chapter": (0, 0),
        "mature_decline_floor": "N",
        "pruning_quota": 9999,
        "net_balance_range": (-9999, -1),
    },
    "multi-pov": {
        "may_plant_per_chapter": (2, 3),
        "mature_decline_floor": "floor(N/4)",
        "pruning_quota": 8,
        "net_balance_range": (0, 0),
    },
}


def get_matrix(volume_type):
    """返回该卷类型的阈值矩阵。未知类型 raise KeyError。"""
    return VOLUME_TYPE_MATRIX[volume_type]
```

- [ ] **Step 4: 实现 `config/config.py`**

```python
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
    # 浅合并：loaded 覆盖 default 的顶层 key
    for k, v in loaded.items():
        default[k] = v
    return default
```

- [ ] **Step 5: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/config/ tests/bedrock/test_config.py
git commit -m "feat(bedrock): config infrastructure (volume_type_matrix + config file)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 卷大纲 amendment（unlock/relock/update_beat_contract + beat 契约结构）

**Files:**
- Modify: `src/bedrock/repositories/outline.py`（追加函数）
- Test: `tests/bedrock/test_amendment.py`

> 此 Task 定义 beat_contracts JSON 结构 + get_beat_contract helper，Task 3 beat 兑现校验依赖。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_amendment.py
import json
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline,
    relock_volume_outline, update_beat_contract, get_beat_contract,
    OutlineLockedError,
)
from src.bedrock.repositories.plot_tree import create_volume


def _seed_volume(conn):
    return create_volume(conn, 1, "v", 1, 3, "opening")


def test_unlock_relock_with_amendment(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    assert get_volume_outline_status(conn, vid) == "locked"
    unlock_volume_outline(conn, vid, reason="修正 beat 契约", author="human")
    assert get_volume_outline_status(conn, vid) == "drafted"
    # amendment 留痕
    ams = conn.execute("SELECT * FROM amendment WHERE entity_type='volume_outline'").fetchall()
    assert len(ams) == 1
    assert ams[0]["reason"] == "修正 beat 契约"
    relock_volume_outline(conn, vid)
    assert get_volume_outline_status(conn, vid) == "locked"
    conn.close()


def test_update_beat_contract_blocked_when_locked(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    with pytest.raises(OutlineLockedError):
        update_beat_contract(conn, vid, beat_id=1,
                             new_contract={"purpose": "x" * 10, "participating_characters": [], "advance_threads": []})
    conn.close()


def test_update_beat_contract_after_unlock(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, reason="加 beat", author="human")
    update_beat_contract(conn, vid, beat_id=1,
                         new_contract={"purpose": "林深发现注记", "participating_characters": ["林深"], "advance_threads": []})
    c = get_beat_contract(conn, vid, beat_id=1)
    assert c["purpose"] == "林深发现注记"
    assert "林深" in c["participating_characters"]
    conn.close()


def get_volume_outline_status(conn, vid):
    return conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (vid,)).fetchone()["status"]
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_amendment.py -v`
Expected: FAIL（ImportError: cannot import name unlock_volume_outline）

- [ ] **Step 3: 追加函数到 `src/bedrock/repositories/outline.py`**（文件末尾，保留现有函数）

```python
# 追加到 src/bedrock/repositories/outline.py 末尾

class OutlineLockedError(Exception):
    pass


def unlock_volume_outline(conn, volume_id, reason, author="human"):
    """locked → drafted。强制记 amendment。"""
    from src.bedrock.repositories.governance import add_amendment
    row = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    if row["status"] != "locked":
        raise ValueError(f"volume_outline status={row['status']}, expected 'locked'")
    add_amendment(conn, entity_type="volume_outline", entity_id=volume_id,
                  field="status", old="locked", new="drafted", reason=reason, author=author)
    conn.execute("UPDATE volume_outline SET status='drafted', locked_at=NULL WHERE volume_id=?",
                 (volume_id,))
    conn.commit()


def relock_volume_outline(conn, volume_id):
    """drafted → locked。"""
    conn.execute("UPDATE volume_outline SET status='locked', locked_at=datetime('now') WHERE volume_id=?",
                 (volume_id,))
    conn.commit()


def _read_beat_contracts(conn, volume_id):
    row = conn.execute("SELECT beat_contracts FROM volume_outline WHERE volume_id=?",
                       (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    return json.loads(row["beat_contracts"])


def _write_beat_contracts(conn, volume_id, contracts):
    conn.execute("UPDATE volume_outline SET beat_contracts=? WHERE volume_id=?",
                 (json.dumps(contracts, ensure_ascii=False), volume_id))
    conn.commit()


def update_beat_contract(conn, volume_id, beat_id, new_contract):
    """修改 beat_contracts JSON 里 beat_id 对应的契约项。locked 下 raise OutlineLockedError。"""
    row = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    if row["status"] == "locked":
        raise OutlineLockedError(f"volume_outline {volume_id} locked；必须先 unlock")
    contracts = _read_beat_contracts(conn, volume_id)
    # 按 beat_id 寻址替换；不存在则 append
    found = False
    for i, c in enumerate(contracts):
        if c.get("beat_id") == beat_id:
            contracts[i] = {"beat_id": beat_id, **new_contract}
            found = True
            break
    if not found:
        contracts.append({"beat_id": beat_id, **new_contract})
    _write_beat_contracts(conn, volume_id, contracts)


def get_beat_contract(conn, volume_id, beat_id):
    """读 beat_contracts 里 beat_id 的契约项。不存在返回 None。"""
    contracts = _read_beat_contracts(conn, volume_id)
    for c in contracts:
        if c.get("beat_id") == beat_id:
            return c
    return None
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_amendment.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/repositories/outline.py tests/bedrock/test_amendment.py
git commit -m "feat(bedrock): outline amendment (unlock/relock/update_beat_contract + beat_contracts structure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: beat 兑现校验

**Files:**
- Create: `src/bedrock/checks/__init__.py`（空）
- Create: `src/bedrock/checks/beat_fulfillment.py`
- Test: `tests/bedrock/test_beat_fulfillment.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_beat_fulfillment.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.beat_fulfillment import check_beat_fulfillment, BeatViolation
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph, update_beat_status,
)
from src.bedrock.repositories.beat_link import link_beat_character
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.suspense import plant_thread, record_consumption
from src.bedrock.repositories.outline import save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract


def _seed_chapter_with_beat(conn, advance_thread_id=None):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的诡异注记")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, reason="setup", author="system")
    return vid, cid, bid


def test_unwritten_beat_violation(tmp_project):
    """beat 仍 planned → unwritten_beat。"""
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    # beat 默认 planned（未写）
    vs = check_beat_fulfillment(conn, cid)
    kinds = [v.kind for v in vs]
    assert "unwritten_beat" in kinds
    conn.close()


def test_missing_character_violation(tmp_project):
    """beat written 但声明角色未在段落出场 → missing_character。"""
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="第二个足够长的场景目的描述")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    # 段落里没提林深
    create_paragraph(conn, chapter_id=cid2, seq=1, text="风吹过空荡的街道，没有任何人。",
                     content_hash="h", beat_id=bid2, role="narrative")
    vs = check_beat_fulfillment(conn, cid2)
    kinds = [v.kind for v in vs]
    assert "missing_character" in kinds
    conn.close()


def test_thread_not_advanced_violation(tmp_project):
    """beat 契约声明 advance_threads 但 thread_consumption 无记录 → thread_not_advanced。"""
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="推进真相线索的场景目的")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1, text="林深看着远方的灯火。",
                     content_hash="h", beat_id=bid2, role="narrative")
    # 声明 advance_threads 但不实际推进
    update_beat_contract(conn, vid, beat_id=bid2,
                         new_contract={"purpose": "推进真相线索的场景目的",
                                       "participating_characters": [], "advance_threads": ["ST001"]})
    vs = check_beat_fulfillment(conn, cid2)
    kinds = [v.kind for v in vs]
    assert "thread_not_advanced" in kinds
    conn.close()


def test_all_good_no_violations(tmp_project):
    """beat written + 角色出场 + 无声明悬链 → 无 violation。"""
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="林深在书摊翻书的场景目的")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1, text="林深蹲下，翻开那本旧书。",
                     content_hash="h", beat_id=bid2, role="narrative")
    vs = check_beat_fulfillment(conn, cid2)
    assert vs == []
    conn.close()
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_beat_fulfillment.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `checks/beat_fulfillment.py`**

```python
# src/bedrock/checks/beat_fulfillment.py
import json
from dataclasses import dataclass
from src.bedrock.repositories.plot_tree import list_beats_in_chapter, list_paragraphs_in_chapter, get_character
from src.bedrock.repositories.beat_link import characters_in_beat
from src.bedrock.repositories.suspense import threads_advanced_at_beat
from src.bedrock.repositories.outline import get_beat_contract


@dataclass
class BeatViolation:
    beat_id: int
    kind: str          # "unwritten_beat" | "missing_character" | "thread_not_advanced"
    detail: str
    fix_hint: str


def _volume_id_of_chapter(conn, chapter_id):
    row = conn.execute("SELECT volume_id FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["volume_id"] if row else None


def check_beat_fulfillment(conn, chapter_id):
    """校验该章所有 beat 的契约兑现。返回 violations 列表（不更新状态）。"""
    violations = []
    beats = list_beats_in_chapter(conn, chapter_id)
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    paras_by_beat = {}
    for p in paragraphs:
        if p["beat_id"] is not None:
            paras_by_beat.setdefault(p["beat_id"], []).append(p)

    volume_id = _volume_id_of_chapter(conn, chapter_id)

    for beat in beats:
        # 规则0: planned→written
        if beat["status"] == "planned":
            violations.append(BeatViolation(
                beat_id=beat["id"], kind="unwritten_beat",
                detail=f"beat {beat['id']} 仍为 planned 状态（未写）",
                fix_hint="写出该 beat 的内容"))
            continue

        # 规则1: 角色出场（beat_character 联结表角色在 beat 段落 grep）
        beat_paras = paras_by_beat.get(beat["id"], [])
        beat_text = "".join(p["text"] for p in beat_paras)
        for link in characters_in_beat(conn, beat["id"]):
            char = get_character(conn, link["character_id"])
            if char is None:
                continue
            names = [char["name"]] + json.loads(char["aliases"])
            if not any(n and n in beat_text for n in names):
                violations.append(BeatViolation(
                    beat_id=beat["id"], kind="missing_character",
                    detail=f"角色 {char['name']} 未在 beat 段落出场",
                    fix_hint=f"在 beat {beat['id']} 段落加入 {char['name']} 的出场"))

        # 规则2: 悬链迁移（beat 契约 advance_threads 声明 vs thread_consumption 实际）
        if volume_id is not None:
            contract = get_beat_contract(conn, volume_id, beat["id"])
            if contract:
                declared = contract.get("advance_threads", [])
                actual = {r["thread_id"] for r in threads_advanced_at_beat(conn, beat["id"])}
                for tid in declared:
                    if tid not in actual:
                        violations.append(BeatViolation(
                            beat_id=beat["id"], kind="thread_not_advanced",
                            detail=f"悬链 {tid} 声明推进但 thread_consumption 无记录",
                            fix_hint=f"在 beat {beat['id']} 推进悬链 {tid}（record_consumption）"))

    return violations
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_beat_fulfillment.py -v`
Expected: 4 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/bedrock/ -v`
Expected: 全部通过（SP1 的 40 + Task1 的 3 + Task2 的 3 + Task3 的 4 = 50）

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/checks/ tests/bedrock/test_beat_fulfillment.py
git commit -m "feat(bedrock): beat fulfillment check (unwritten/missing_character/thread_not_advanced)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 跨卷锚点校验

**Files:**
- Create: `src/bedrock/checks/cross_volume.py`
- Test: `tests/bedrock/test_cross_volume.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_cross_volume.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.cross_volume import check_cross_volume_anchors, CrossVolumeDebtReport, Anchor
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.suspense import plant_thread
from src.bedrock.repositories.outline import save_master_outline


def test_high_overdue_thread_blocks(tmp_project):
    """planned_resolve_volume<=V 且未 resolved 的 high 悬链 → blocking。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    # high 悬链，应在本卷回收但未回收
    plant_thread(conn, content="x", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 1
    assert report.blocking[0].kind == "thread_overdue"
    conn.close()


def test_medium_overdue_thread_advisory(tmp_project):
    """medium 悬链未回收 → advisory（不阻断）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="medium",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 0
    assert len(report.advisory) == 1
    conn.close()


def test_null_planned_resolve_volume_not_flagged(tmp_project):
    """planned_resolve_volume IS NULL → 无跨卷承诺，不判逾期。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent")  # 无 planned_resolve_volume
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 0
    assert len(report.advisory) == 0
    conn.close()


def test_milestone_unmet_blocks_when_high(tmp_project):
    """里程碑 resolves_threads 含未 resolved 的 high 悬链 → blocking。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=bid, origin="emergent")  # 未 resolved
    save_master_outline(conn, key_milestones=[
        {"name": "觉醒", "expected_volume": 1, "resolves_threads": [tid]}])
    report = check_cross_volume_anchors(conn, 1)
    assert any(a.kind == "milestone_unmet" for a in report.blocking)
    conn.close()
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_cross_volume.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `checks/cross_volume.py`**

```python
# src/bedrock/checks/cross_volume.py
import json
from dataclasses import dataclass, field
from src.bedrock.repositories.outline import get_master_outline


@dataclass
class Anchor:
    kind: str          # "thread_overdue" | "milestone_unmet"
    ref_id: str        # 悬链 id 或里程碑 name
    importance: str    # high/medium/low
    detail: str


@dataclass
class CrossVolumeDebtReport:
    blocking: list = field(default_factory=list)   # high 未兑现
    advisory: list = field(default_factory=list)   # medium/low 未兑现


def _classify(anchor, report):
    if anchor.importance == "high":
        report.blocking.append(anchor)
    else:
        report.advisory.append(anchor)


def check_cross_volume_anchors(conn, volume_id):
    """卷收尾时检查跨卷锚点兑现。high 未兑现 → blocking；其他 → advisory。"""
    report = CrossVolumeDebtReport()

    # 1. 悬链 planned_resolve_volume 兑现
    rows = conn.execute(
        "SELECT id, content, importance, status FROM suspense_thread "
        "WHERE planned_resolve_volume IS NOT NULL AND planned_resolve_volume <= ? "
        "AND status NOT IN ('resolved','abandoned')",
        (volume_id,)).fetchall()
    for r in rows:
        _classify(Anchor(
            kind="thread_overdue", ref_id=str(r["id"]),
            importance=r["importance"],
            detail=f"悬链 {r['id']}（{r['content'][:20]}）应于卷{volume_id}回收但 status={r['status']}"),
            report)

    # 2. 里程碑兑现
    mo = get_master_outline(conn)
    if mo:
        milestones = json.loads(mo["key_milestones"]) if mo["key_milestones"] else []
        for ms in milestones:
            if ms.get("expected_volume") != volume_id:
                continue
            resolves = ms.get("resolves_threads", [])
            if not resolves:
                continue
            # 查这些悬链是否都 resolved + 取最高 importance
            placeholders = ",".join("?" * len(resolves))
            threads = conn.execute(
                f"SELECT id, importance, status FROM suspense_thread WHERE id IN ({placeholders})",
                resolves).fetchall()
            unmet = [t for t in threads if t["status"] != "resolved"]
            if unmet:
                max_imp = _max_importance([t["importance"] for t in unmet])
                _classify(Anchor(
                    kind="milestone_unmet", ref_id=ms.get("name", "?"),
                    importance=max_imp,
                    detail=f"里程碑 {ms.get('name')} 的 resolves_threads 有 {len(unmet)} 条未 resolved"),
                    report)

    return report


def _max_importance(importances):
    rank = {"high": 3, "medium": 2, "low": 1}
    return max(importances, key=lambda i: rank.get(i, 0))
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_cross_volume.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/checks/cross_volume.py tests/bedrock/test_cross_volume.py
git commit -m "feat(bedrock): cross-volume anchor check (high blocking / others advisory)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: deviated/override 入口

**Files:**
- Modify: `src/bedrock/repositories/plot_tree.py`（追加 mark_override）
- Test: `tests/bedrock/test_override.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_override.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, update_beat_status, mark_override, get_beat,
)


def _seed_beat(conn, status="deviated"):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    update_beat_status(conn, bid, status)
    return bid


def test_override_deviated_with_amendment(tmp_project):
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "deviated")
    mark_override(conn, bid, reason="人工兜底，剧情需要", author="human")
    assert get_beat(conn, bid)["status"] == "overridden"
    ams = conn.execute("SELECT * FROM amendment WHERE entity_type='beat' AND entity_id=?", (bid,)).fetchall()
    assert len(ams) == 1
    assert ams[0]["new_value"] == "overridden"
    conn.close()


def test_override_written_also_allowed(tmp_project):
    """放宽：written 状态也可 override（人工兜底）。"""
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "written")
    mark_override(conn, bid, reason="跳过校验", author="human")
    assert get_beat(conn, bid)["status"] == "overridden"
    conn.close()


def test_override_rejected_for_verified(tmp_project):
    """verified 状态不能 override（已通过校验，无需逃逸）。"""
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "verified")
    with pytest.raises(ValueError):
        mark_override(conn, bid, reason="x", author="human")
    conn.close()
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_override.py -v`
Expected: FAIL（ImportError: cannot import name mark_override）

- [ ] **Step 3: 追加 `mark_override` 到 `src/bedrock/repositories/plot_tree.py` 末尾**

```python
# 追加到 src/bedrock/repositories/plot_tree.py 末尾

def mark_override(conn, beat_id, reason, author="human"):
    """beat.status ∈ {deviated, written} → overridden。强制记 amendment（逃逸审计）。"""
    from src.bedrock.repositories.governance import add_amendment
    row = conn.execute("SELECT status FROM beat WHERE id=?", (beat_id,)).fetchone()
    if row is None:
        raise ValueError(f"beat {beat_id} not found")
    if row["status"] not in ("deviated", "written"):
        raise ValueError(f"beat {beat_id} status={row['status']}，仅 deviated/written 可 override")
    add_amendment(conn, entity_type="beat", entity_id=beat_id,
                  field="status", old=row["status"], new="overridden", reason=reason, author=author)
    conn.execute("UPDATE beat SET status='overridden' WHERE id=?", (beat_id,))
    conn.commit()
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_override.py -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/bedrock/ -v`
Expected: 全部通过（SP1 40 + SP2 Task1-5 共 17 = 57）

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/repositories/plot_tree.py tests/bedrock/test_override.py
git commit -m "feat(bedrock): beat override entrypoint (deviated/written -> overridden + amendment)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 自检

**1. Spec 覆盖**：
- §① beat 兑现校验 → Task 3（含 unwritten_beat/missing_character/thread_not_advanced 三规则）✓
- §② amendment → Task 2（unlock/relock/update_beat_contract/OutlineLockedError/beat_contracts 结构/get_beat_contract）✓
- §③ 跨卷锚点 → Task 4（thread_overdue/milestone_unmet，high blocking/其他 advisory，NULL 放行）✓
- §④ override → Task 5（mark_override，deviated/written 放宽，verified 拒绝）✓
- §⑤ 配置基础设施 → Task 1（volume_type_matrix 静态常量 + config 文件机制）✓
- SP5 标记（章级配额/mature/pruning/端到端测试）→ 不在本 plan，spec §4 已标注 ✓

**2. Placeholder 扫描**：无 TBD/TODO；所有步骤含完整代码与命令。

**3. 类型/签名一致性**：
- `check_beat_fulfillment(conn, chapter_id) → list[BeatViolation]`（Task 3 定义，测试用）
- `BeatViolation(beat_id, kind, detail, fix_hint)`（Task 3 定义）
- `check_cross_volume_anchors(conn, volume_id) → CrossVolumeDebtReport`（Task 4）
- `CrossVolumeDebtReport.blocking/advisory: list[Anchor]`，`Anchor(kind, ref_id, importance, detail)`（Task 4）
- `mark_override(conn, beat_id, reason, author="human")`（Task 5）
- `update_beat_contract(conn, volume_id, beat_id, new_contract)` / `get_beat_contract(conn, volume_id, beat_id)`（Task 2）
- `OutlineLockedError`（Task 2 定义，Task 3 不依赖）
- Task 3 的 `get_beat_contract` import 自 Task 2 的 outline.py ✓
- Task 3/4 的 SP1 repo 函数（list_beats_in_chapter/characters_in_beat/threads_advanced_at_beat/get_master_outline 等）均在 SP1 已实现 ✓

**4. 依赖顺序**：Task 2（beat_contracts 结构 + get_beat_contract）先于 Task 3（beat 兑现校验依赖 get_beat_contract）。Task 1（配置）独立。Task 4/5 独立。顺序 1→2→3→4→5 满足依赖。

**5. SP5 标记确认**：volume_type_matrix 在 Task 1 建常量但不查询（查询在 SP5）；config 机制 Task 1 建基础设施。本 plan 不做配额/mature/pruning 检查。

---

## 执行交接

计划完成，保存于 `docs/superpowers/plans/2026-06-14-bedrock-sp2-anti-drift.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每 Task 派新子代理，任务间 review

**2. Inline Execution** — 当前会话用 executing-plans 批量 + checkpoint

选哪种？
