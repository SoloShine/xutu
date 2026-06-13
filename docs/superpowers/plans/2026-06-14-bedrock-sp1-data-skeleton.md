# 小说管线 V3 — SP1 数据骨架 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建独立 package `src/bedrock/`，落地 SQLite 单存储 schema（全实体 + 联结表 + 约束）+ 数据访问层 + 跨字段校验 + 新作品初始化。不含业务逻辑（beat 兑现校验/重算/agent 编排属后续 SP）。

**Architecture:** stdlib `sqlite3`（WAL 模式）+ `dataclasses`，零外部依赖。schema 用单一 `schema.sql`（git diff 友好，逐步追加），migration runner 跟踪 `schema_version`。数据访问用 repository 模式，每域一模块。跨字段约束（SQLite CHECK 表达不了的）走 Python validator。

**Tech Stack:** Python 3.10+ stdlib（sqlite3 / dataclasses / pathlib / hashlib / re），pytest。

**前置 spec:** `docs/superpowers/specs/2026-06-14-bedrock-design.md`（§3 全 schema）

---

## 文件结构

```
src/bedrock/
├── __init__.py
├── db/
│   ├── __init__.py
│   ├── connection.py          # SQLite 连接（WAL/pragma），get_connection(project_dir)
│   ├── schema.sql             # 全量 DDL（逐步追加）
│   └── migrate.py             # migration runner（apply schema.sql + schema_version 跟踪）
├── enums.py                   # 所有枚举（volume_type/pronoun/status/thread_type/...）
├── repositories/
│   ├── __init__.py
│   ├── plot_tree.py           # Volume/Chapter/Beat/Paragraph CRUD
│   ├── suspense.py            # SuspenseThread + consumption/planting/advance 联结
│   ├── worldbook.py           # constants/locations/neighbors/time_periods/factions/themes/motifs
│   ├── character.py           # Character + secrets/knowledge/pronoun_overrides/character_faction
│   ├── relation.py            # Relation + entity_state_log
│   ├── event.py               # Event + event_character/event_reveal/event_cause
│   ├── outline.py             # volume_outline + master_outline
│   ├── governance.py          # Amendment + ExportManifest
│   └── telemetry.py           # ChapterMetrics + ChapterRuntime + StyleTemplate
├── validation.py              # 跨字段校验（pronoun-gender/resolved-beat/narrative-beat 等）
└── init_project.py            # 新作品初始化（建空 DB + schema）
tests/bedrock/
├── conftest.py                # tmp project fixture
├── ...（每域一测试文件）
```

**设计原则：** 每个文件单一职责；repository 模块按域聚合（同域实体在一起变更）；schema.sql 单一文件逐步增长；测试用 tmp 目录隔离。

---

## Task 1: Package 骨架 + DB 连接 + Migration Runner + Enums

**Files:**
- Create: `src/bedrock/__init__.py`
- Create: `src/bedrock/enums.py`
- Create: `src/bedrock/db/__init__.py`
- Create: `src/bedrock/db/connection.py`
- Create: `src/bedrock/db/schema.sql`（初始只有 schema_version 表）
- Create: `src/bedrock/db/migrate.py`
- Create: `tests/bedrock/__init__.py`
- Create: `tests/bedrock/conftest.py`
- Test: `tests/bedrock/test_db.py`

- [ ] **Step 1: 写失败测试（连接 + migration）**

```python
# tests/bedrock/test_db.py
import sqlite3
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.db.migrate import apply_migrations


def test_get_connection_opens_sqlite_with_wal(tmp_project):
    conn = get_connection(tmp_project)
    assert isinstance(conn, sqlite3.Connection)
    # WAL 模式
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_apply_migrations_creates_schema_version(tmp_project):
    apply_migrations(tmp_project)
    conn = get_connection(tmp_project)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "schema_version" in tables
    ver = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert ver >= 1
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_db.py -v`
Expected: FAIL（`ModuleNotFoundError: src.bedrock.db.connection`）

- [ ] **Step 3: 实现 enums.py**

```python
# src/bedrock/enums.py
from enum import Enum


class VolumeType(str, Enum):
    OPENING = "opening"
    ADVANCING = "advancing"
    CLIMAX = "climax"
    EPILOGUE = "epilogue"
    MULTI_POV = "multi-pov"


class VolumeStatus(str, Enum):
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ChapterStatus(str, Enum):
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETED = "completed"


class BeatStatus(str, Enum):
    PLANNED = "planned"
    WRITTEN = "written"
    VERIFIED = "verified"
    DEVIATED = "deviated"
    OVERRIDDEN = "overridden"


class ParagraphRole(str, Enum):
    NARRATIVE = "narrative"
    TRANSITION = "transition"
    AMBIENT = "ambient"
    NARRATION = "narration"


class Pronoun(str, Enum):
    HE = "他"
    SHE = "她"
    IT = "它"
    DIVINE = "祂"
    TA = "TA"


class Gender(str, Enum):
    MALE = "男"
    FEMALE = "女"
    NONE = "无"
    UNKNOWN = "未知"
    OTHER = "其他"


class CharacterState(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    DECEASED = "deceased"
    ASCENDED = "ascended"
    MERGED = "merged"


class VisibilityMode(str, Enum):
    PUBLIC = "public"
    SECRET_UNTIL = "secret_until"
    FACTION = "faction"
    CHARACTERS = "characters"


class VisibilityAxis(str, Enum):
    CHARACTER_EPISTEMIC = "character_epistemic"
    READER_DISCLOSURE = "reader_disclosure"


class ThreadType(str, Enum):
    MYSTERY = "mystery"
    FORESHADOWING = "foreshadowing"
    CHARACTER_ARC = "character_arc"
    THEME_ARC = "theme_arc"
    PLOT_ARC = "plot_arc"


class ThreadStatus(str, Enum):
    SCHEDULED = "scheduled"
    PLANTED = "planted"
    DEVELOPING = "developing"
    MATURE = "mature"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class ThreadOrigin(str, Enum):
    SCHEDULED = "scheduled"
    EMERGENT = "emergent"


class EventType(str, Enum):
    PLOT = "plot"
    TURNING = "turning"
    REVELATION = "revelation"
    CLIMAX = "climax"
    GAP = "gap"
    DENOUEMENT = "denouement"


class OutlineStatus(str, Enum):
    DRAFTED = "drafted"
    LOCKED = "locked"
    WRITING = "writing"
    COMPLETED = "completed"


class InspirationStatus(str, Enum):
    RAW = "raw"
    REFINED = "refined"
    CONSUMED = "consumed"
    PARTIAL = "partial"
    DISCARDED = "discarded"


class ExportScope(str, Enum):
    CHAPTER = "chapter"
    VOLUME = "volume"
    BOOK = "book"


class ExportStatus(str, Enum):
    DRAFT = "draft"
    FINAL = "final"
    PUBLISHED = "published"


class MetricSource(str, Enum):
    SYSTEM_RECOMPUTED = "system_recomputed"


# 悬链状态机合法迁移图（供后续 SP 的迁移校验用；SP1 只定义）
LEGAL_THREAD_TRANSITIONS = {
    ThreadStatus.SCHEDULED: {ThreadStatus.PLANTED, ThreadStatus.ABANDONED},
    ThreadStatus.PLANTED: {ThreadStatus.DEVELOPING, ThreadStatus.ABANDONED, ThreadStatus.RESOLVED},
    ThreadStatus.DEVELOPING: {ThreadStatus.MATURE, ThreadStatus.PARTIALLY_RESOLVED, ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.MATURE: {ThreadStatus.PARTIALLY_RESOLVED, ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.PARTIALLY_RESOLVED: {ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.RESOLVED: set(),
    ThreadStatus.ABANDONED: set(),
}
```

- [ ] **Step 4: 实现 connection.py**

```python
# src/bedrock/db/connection.py
import sqlite3
from pathlib import Path

DB_FILENAME = "bedrock.db"


def get_connection(project_dir: Path) -> sqlite3.Connection:
    """打开项目 DB（WAL + 外键开启）。调用方负责 close。"""
    db_path = Path(project_dir) / DB_FILENAME
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

- [ ] **Step 5: 实现 schema.sql 初始（schema_version 表）**

```sql
-- src/bedrock/db/schema.sql
-- V3 数据骨架 schema。逐步追加（每个 Task 往此文件追加 DDL）。

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 6: 实现 migrate.py**

```python
# src/bedrock/db/migrate.py
import sqlite3
from pathlib import Path
from src.bedrock.db.connection import get_connection

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()
    return row[0] or 0


def apply_migrations(project_dir: Path) -> int:
    """应用 schema.sql。幂等——按内容哈希判断是否已应用。返回应用后的 version。"""
    sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    content_hash = _hash_sql(sql)
    conn = get_connection(project_dir)
    try:
        conn.executescript(sql)
        # version = 内容哈希的稳定整数；同一 schema.sql 只记录一次
        version = _stable_version(content_hash)
        existing = conn.execute(
            "SELECT 1 FROM schema_version WHERE version=?", (version,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO schema_version(version) VALUES (?)", (version,)
            )
            conn.commit()
        return version
    finally:
        conn.close()


def _hash_sql(sql: str) -> str:
    import hashlib
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def _stable_version(content_hash: str) -> int:
    # 把 12 位 hex 前几位转成 int（够区分）
    return int(content_hash[:8], 16) % 1000000
```

- [ ] **Step 7: 实现 conftest.py（tmp project fixture）**

```python
# tests/bedrock/conftest.py
import pytest
from pathlib import Path
from src.bedrock.db.migrate import apply_migrations


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """空项目目录，已 apply schema。"""
    apply_migrations(tmp_path)
    return tmp_path
```

- [ ] **Step 8: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_db.py -v`
Expected: PASS（2 passed）

- [ ] **Step 9: Commit**

```bash
git add src/bedrock/ tests/bedrock/
git commit -m "feat(bedrock): package skeleton, DB connection, migration runner, enums"
```

---

## Task 2: 剧情树 Schema（Volume / Chapter / Beat / Paragraph）

**Files:**
- Modify: `src/bedrock/db/schema.sql`（追加 4 表）
- Test: `tests/bedrock/test_schema_plot_tree.py`

- [ ] **Step 1: 写失败测试（约束验证）**

```python
# tests/bedrock/test_schema_plot_tree.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection


def test_volume_number_unique(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute(
        "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
        "VALUES(1,'萌动',1,12,'opening','planned')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
            "VALUES(1,'重复',1,12,'opening','planned')")
    conn.close()


def test_chapter_global_number_unique(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
                 "VALUES(1,'v',1,12,'opening','planned')")
    vol_id = conn.execute("SELECT id FROM volume WHERE number=1").fetchone()[0]
    conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t','planned')", (vol_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t2','planned')", (vol_id,))
    conn.close()


def test_paragraph_narrative_must_have_beat(tmp_project):
    """role=narrative 时 beat_id 不可空（CHECK）。"""
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
                 "VALUES(1,'v',1,12,'opening','planned')")
    vol_id = conn.execute("SELECT id FROM volume WHERE number=1").fetchone()[0]
    conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t','planned')", (vol_id,))
    ch_id = conn.execute("SELECT id FROM chapter WHERE global_number=1").fetchone()[0]
    # narrative + beat_id NULL 应被拒
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
            "VALUES(?,1,'x','h',NULL,'narrative')", (ch_id,))
    # transition + beat_id NULL 允许
    conn.execute(
        "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
        "VALUES(?,1,'x','h',NULL,'transition')", (ch_id,))
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_schema_plot_tree.py -v`
Expected: FAIL（`no such table: volume`）

- [ ] **Step 3: 追加 schema DDL 到 schema.sql**

```sql
-- 追加到 src/bedrock/db/schema.sql 末尾

CREATE TABLE IF NOT EXISTS volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    chapter_start INTEGER NOT NULL,
    chapter_end INTEGER NOT NULL,
    volume_type TEXT NOT NULL CHECK (volume_type IN ('opening','advancing','climax','epilogue','multi-pov')),
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','writing','completed','archived')),
    theme_seeds TEXT NOT NULL DEFAULT '[]',   -- JSON array
    CHECK (chapter_start <= chapter_end)
);

CREATE TABLE IF NOT EXISTS chapter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id INTEGER NOT NULL REFERENCES volume(id),
    global_number INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','writing','completed'))
);

CREATE TABLE IF NOT EXISTS beat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapter(id),
    sequence INTEGER NOT NULL,
    purpose TEXT NOT NULL CHECK (length(purpose) >= 10),
    pov_character_id INTEGER,  -- FK 到 character，character 表后续 Task 建；此处先不加 REFERENCES 避免前向依赖
    scene_setting TEXT NOT NULL DEFAULT '{}',  -- JSON {location_id, time_period}
    story_time TEXT,
    timeline_id TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','written','verified','deviated','overridden')),
    deviation_note TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(chapter_id, sequence)
);

CREATE TABLE IF NOT EXISTS paragraph (
    para_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapter(id),
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    beat_id INTEGER REFERENCES beat(id),
    role TEXT NOT NULL CHECK (role IN ('narrative','transition','ambient','narration')),
    UNIQUE(chapter_id, seq),
    -- narrative 段落必须挂 beat
    CHECK (beat_id IS NOT NULL OR role IN ('transition','ambient','narration'))
);
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_schema_plot_tree.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql tests/bedrock/test_schema_plot_tree.py
git commit -m "feat(bedrock): plot tree schema (volume/chapter/beat/paragraph) with constraints"
```

---

## Task 3: 剧情树 Repository（CRUD）

**Files:**
- Create: `src/bedrock/repositories/__init__.py`
- Create: `src/bedrock/repositories/plot_tree.py`
- Test: `tests/bedrock/test_repo_plot_tree.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_repo_plot_tree.py
import pytest
from src.bedrock.repositories.plot_tree import (
    create_volume, get_volume, create_chapter, create_beat, create_paragraph,
    list_paragraphs_in_chapter,
)


def test_volume_crud(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, number=1, name="萌动", chapter_start=1, chapter_end=12,
                        volume_type="opening", theme_seeds=["知识的引力"])
    v = get_volume(conn, vid)
    assert v["name"] == "萌动"
    assert v["chapter_start"] == 1
    conn.close()


def test_chapter_beat_paragraph_roundtrip(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="开端")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的诡异注记")
    create_paragraph(conn, chapter_id=cid, seq=1, text="周末清晨，林深走出公寓。",
                     content_hash="h1", beat_id=bid, role="narrative")
    create_paragraph(conn, chapter_id=cid, seq=2, text="三天后，他回到书摊。",
                     content_hash="h2", beat_id=None, role="transition")
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["seq"] for p in paras] == [1, 2]
    assert paras[0]["beat_id"] == bid
    assert paras[1]["beat_id"] is None
    conn.close()


def test_beat_purpose_too_short_rejected(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    with pytest.raises(Exception):
        create_beat(conn, chapter_id=cid, sequence=1, purpose="太短")  # <10 字符
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_repo_plot_tree.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 plot_tree.py repository**

```python
# src/bedrock/repositories/plot_tree.py
import json
import sqlite3
from typing import Optional


def create_volume(conn: sqlite3.Connection, number: int, name: str,
                  chapter_start: int, chapter_end: int, volume_type: str,
                  theme_seeds: Optional[list] = None) -> int:
    cur = conn.execute(
        "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,theme_seeds) "
        "VALUES(?,?,?,?,?,?)",
        (number, name, chapter_start, chapter_end, volume_type,
         json.dumps(theme_seeds or [], ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def get_volume(conn: sqlite3.Connection, volume_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM volume WHERE id=?", (volume_id,)).fetchone()


def create_chapter(conn: sqlite3.Connection, volume_id: int, global_number: int,
                   title: str, status: str = "planned") -> int:
    cur = conn.execute(
        "INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,?,?,?)",
        (volume_id, global_number, title, status))
    conn.commit()
    return cur.lastrowid


def get_chapter_by_global(conn: sqlite3.Connection, global_number: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM chapter WHERE global_number=?",
                        (global_number,)).fetchone()


def create_beat(conn: sqlite3.Connection, chapter_id: int, sequence: int,
                purpose: str, pov_character_id: Optional[int] = None,
                scene_setting: Optional[dict] = None, story_time: Optional[str] = None,
                timeline_id: Optional[str] = None, status: str = "planned") -> int:
    cur = conn.execute(
        "INSERT INTO beat(chapter_id,sequence,purpose,pov_character_id,scene_setting,"
        "story_time,timeline_id,status) VALUES(?,?,?,?,?,?,?,?)",
        (chapter_id, sequence, purpose, pov_character_id,
         json.dumps(scene_setting or {}, ensure_ascii=False), story_time, timeline_id, status))
    conn.commit()
    return cur.lastrowid


def get_beat(conn: sqlite3.Connection, beat_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM beat WHERE id=?", (beat_id,)).fetchone()


def list_beats_in_chapter(conn: sqlite3.Connection, chapter_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM beat WHERE chapter_id=? ORDER BY sequence", (chapter_id,)).fetchall()


def update_beat_status(conn: sqlite3.Connection, beat_id: int, status: str,
                       deviation_note: Optional[str] = None) -> None:
    conn.execute(
        "UPDATE beat SET status=?, deviation_note=COALESCE(?, deviation_note) WHERE id=?",
        (status, deviation_note, beat_id))
    conn.commit()


def create_paragraph(conn: sqlite3.Connection, chapter_id: int, seq: int,
                     text: str, content_hash: str, beat_id: Optional[int],
                     role: str) -> int:
    cur = conn.execute(
        "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
        "VALUES(?,?,?,?,?,?)",
        (chapter_id, seq, text, content_hash, beat_id, role))
    conn.commit()
    return cur.lastrowid


def list_paragraphs_in_chapter(conn: sqlite3.Connection, chapter_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM paragraph WHERE chapter_id=? ORDER BY seq",
        (chapter_id,)).fetchall()


def update_paragraph(conn: sqlite3.Connection, para_id: int, text: str,
                     content_hash: str, beat_id: Optional[int], role: str) -> None:
    conn.execute(
        "UPDATE paragraph SET text=?, content_hash=?, beat_id=?, role=? WHERE para_id=?",
        (text, content_hash, beat_id, role, para_id))
    conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_repo_plot_tree.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/repositories/ tests/bedrock/test_repo_plot_tree.py
git commit -m "feat(bedrock): plot tree repository CRUD"
```

---

## Task 4: 角色面/世界书前置 — Character Schema（Secrets/Knowledge/Pronoun/Character_Faction）

> 角色表被 beat.pov_character_id、event、relation 等多处引用，先于它们建立。

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Test: `tests/bedrock/test_schema_character.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_schema_character.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection


def test_pronoun_not_null(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO character(name,gender,role,state) VALUES('林深','男','protagonist','active')")
    conn.close()


def test_character_secret_visibility_mode_check(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) VALUES('林深','他','男','protagonist','active')")
    cid = conn.execute("SELECT id FROM character WHERE name='林深'").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis) "
                     "VALUES(?,'k','v','bogus','character_epistemic')", (cid,))
    conn.close()


def test_pronoun_override_logs_change(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) VALUES('T-1','它','无','supporting','active')")
    cid = conn.execute("SELECT id FROM character WHERE name='T-1'").fetchone()[0]
    conn.execute("INSERT INTO pronoun_override(character_id,from_chapter,pronoun,reason) "
                 "VALUES(?,50,'祂','觉醒后变更')", (cid,))
    rows = conn.execute("SELECT * FROM pronoun_override WHERE character_id=?", (cid,)).fetchall()
    assert len(rows) == 1
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_schema_character.py -v`
Expected: FAIL（`no such table: character`）

- [ ] **Step 3: 追加 character schema 到 schema.sql**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS character (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    aliases TEXT NOT NULL DEFAULT '[]',   -- JSON array
    pronoun TEXT NOT NULL CHECK (pronoun IN ('他','她','它','祂','TA')),
    gender TEXT CHECK (gender IS NULL OR gender IN ('男','女','无','未知','其他')),
    role TEXT NOT NULL CHECK (role IN ('protagonist','supporting','antagonist','minor')),
    faction_id INTEGER,   -- FK 到 faction（后续 Task 建表后加 REFERENCES；此处用应用层校验）
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','dormant','deceased','ascended','merged')),
    personality TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    abilities TEXT NOT NULL DEFAULT '[]'   -- JSON array
);

-- secrets：敏感信息集合，带可见性双轴
CREATE TABLE IF NOT EXISTS character_secret (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    vis_mode TEXT NOT NULL CHECK (vis_mode IN ('public','secret_until','faction','characters')),
    vis_ref TEXT NOT NULL DEFAULT '{}',   -- JSON: reveal_chapter / faction_id / [character_id...]
    vis_axis TEXT NOT NULL CHECK (vis_axis IN ('character_epistemic','reader_disclosure')),
    UNIQUE(character_id, key, vis_axis)
);

-- knowledge_state：结构化，精确时序
CREATE TABLE IF NOT EXISTS character_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    fact_id TEXT NOT NULL,
    learned_at_beat INTEGER,   -- FK beat（后加 REFERENCES）
    confidence REAL NOT NULL DEFAULT 1.0,
    decay REAL NOT NULL DEFAULT 0.0,
    UNIQUE(character_id, fact_id)
);

-- pronoun_overrides：极少数代词变更显式留痕
CREATE TABLE IF NOT EXISTS pronoun_override (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    from_chapter INTEGER NOT NULL,
    pronoun TEXT NOT NULL CHECK (pronoun IN ('他','她','它','祂','TA')),
    reason TEXT NOT NULL
);

-- character_faction 联结（角色归属，可随时间变）
CREATE TABLE IF NOT EXISTS character_faction (
    character_id INTEGER NOT NULL REFERENCES character(id),
    faction_id INTEGER NOT NULL,   -- FK faction（后续 Task）
    period_start INTEGER,
    period_end INTEGER,
    PRIMARY KEY(character_id, faction_id, period_start)
);
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_schema_character.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql tests/bedrock/test_schema_character.py
git commit -m "feat(bedrock): character schema (secrets/knowledge/pronoun_overrides/character_faction)"
```

---

## Task 5: Character Repository + 可见性过滤查询

**Files:**
- Create: `src/bedrock/repositories/character.py`
- Test: `tests/bedrock/test_repo_character.py`

- [ ] **Step 1: 写失败测试（含可见性过滤）**

```python
# tests/bedrock/test_repo_character.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.character import (
    create_character, get_character, add_secret,
    visible_secrets_for_context, set_pronoun_override,
)


def _seed_factionless_char(conn, name, pronoun="他", gender="男"):
    return create_character(conn, name=name, pronoun=pronoun, gender=gender,
                            role="protagonist", state="active")


def test_visible_secrets_filters_by_chapter_and_pov(tmp_project):
    conn = get_connection(tmp_project)
    a = _seed_factionless_char(conn, "林深", "他", "男")
    b = _seed_factionless_char(conn, "拾", "她", "女")
    # secret_until ch50
    add_secret(conn, a, key="真实性别", value="女",
               vis_mode="secret_until", vis_ref={"reveal_chapter": 50},
               vis_axis="reader_disclosure")
    # characters-only：只有 b 知道
    add_secret(conn, a, key="卧底身份", value="反派卧底",
               vis_mode="characters", vis_ref={"character_ids": [b]},
               vis_axis="character_epistemic")
    # public
    add_secret(conn, a, key="公开过往", value="曾入伍",
               vis_mode="public", vis_ref={},
               vis_axis="reader_disclosure")

    # ch10，POV=b：只看到 public（secret_until 没到 50；characters 项 b 知道但 axis=character_epistemic，
    # 对 reader_disclosure 视角查询不返回；这里测 character_epistemic 视角）
    ep_seen = visible_secrets_for_context(conn, a, chapter=10, pov_character_id=b,
                                          axis="character_epistemic")
    keys_ep = {s["key"] for s in ep_seen}
    assert "卧底身份" in keys_ep   # b 是知情角色
    assert "真实性别" not in keys_ep

    rd_seen = visible_secrets_for_context(conn, a, chapter=60, pov_character_id=b,
                                          axis="reader_disclosure")
    keys_rd = {s["key"] for s in rd_seen}
    assert "真实性别" in keys_rd   # ch60 > 50，已揭露
    assert "公开过往" in keys_rd
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_repo_character.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 character.py repository**

```python
# src/bedrock/repositories/character.py
import json
import sqlite3
from typing import Optional


def create_character(conn: sqlite3.Connection, name: str, pronoun: str,
                     role: str, gender: Optional[str] = None,
                     aliases: Optional[list] = None, faction_id: Optional[int] = None,
                     state: str = "active", personality: str = "", goals: str = "",
                     abilities: Optional[list] = None) -> int:
    cur = conn.execute(
        "INSERT INTO character(name,aliases,pronoun,gender,role,faction_id,state,personality,goals,abilities) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (name, json.dumps(aliases or [], ensure_ascii=False), pronoun, gender, role,
         faction_id, state, personality, goals,
         json.dumps(abilities or [], ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def get_character(conn: sqlite3.Connection, character_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone()


def get_character_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM character WHERE name=?", (name,)).fetchone()


def add_secret(conn: sqlite3.Connection, character_id: int, key: str, value: str,
               vis_mode: str, vis_ref: dict, vis_axis: str) -> int:
    cur = conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_ref,vis_axis) "
        "VALUES(?,?,?,?,?,?)",
        (character_id, key, value, vis_mode,
         json.dumps(vis_ref, ensure_ascii=False), vis_axis))
    conn.commit()
    return cur.lastrowid


def visible_secrets_for_context(conn: sqlite3.Connection, character_id: int,
                                chapter: int, pov_character_id: Optional[int],
                                axis: str) -> list[sqlite3.Row]:
    """boot context 注入用：按当前章 + POV + axis 过滤该角色的可见 secrets。"""
    rows = conn.execute(
        "SELECT * FROM character_secret WHERE character_id=? AND vis_axis=?",
        (character_id, axis)).fetchall()
    out = []
    for r in rows:
        ref = json.loads(r["vis_ref"])
        if r["vis_mode"] == "public":
            out.append(r)
        elif r["vis_mode"] == "secret_until":
            if chapter >= ref.get("reveal_chapter", 10**9):
                out.append(r)
        elif r["vis_mode"] == "faction":
            # 简化：POV 角色归属该 faction 则可见（faction 校验需 character_faction 查询）
            fid = ref.get("faction_id")
            if fid and pov_character_id:
                in_faction = conn.execute(
                    "SELECT 1 FROM character_faction WHERE character_id=? AND faction_id=?",
                    (pov_character_id, fid)).fetchone()
                if in_faction:
                    out.append(r)
        elif r["vis_mode"] == "characters":
            ids = ref.get("character_ids", [])
            if pov_character_id in ids:
                out.append(r)
    return out


def set_pronoun_override(conn: sqlite3.Connection, character_id: int,
                         from_chapter: int, pronoun: str, reason: str) -> int:
    cur = conn.execute(
        "INSERT INTO pronoun_override(character_id,from_chapter,pronoun,reason) "
        "VALUES(?,?,?,?)", (character_id, from_chapter, pronoun, reason))
    conn.commit()
    return cur.lastrowid


def effective_pronoun(conn: sqlite3.Connection, character_id: int, chapter: int) -> str:
    """返回该角色在某章的有效代词（考虑 override）。"""
    row = conn.execute(
        "SELECT pronoun FROM pronoun_override WHERE character_id=? AND from_chapter<=? "
        "ORDER BY from_chapter DESC LIMIT 1", (character_id, chapter)).fetchone()
    if row:
        return row["pronoun"]
    base = get_character(conn, character_id)
    return base["pronoun"] if base else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_repo_character.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/repositories/character.py tests/bedrock/test_repo_character.py
git commit -m "feat(bedrock): character repository + visibility-filtered secret queries"
```

---

## Task 6: Worldbook Schema + Repository（Constants/Locations/Factions/Time_Periods/Themes/Motifs）

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/worldbook.py`
- Test: `tests/bedrock/test_worldbook.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_worldbook.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.worldbook import (
    add_constant, get_constant, add_location, add_neighbor, neighbors_of,
    add_faction, add_theme,
)


def test_constants_unique_key(tmp_project):
    conn = get_connection(tmp_project)
    add_constant(conn, key="载波频率", value="7.83Hz")
    with pytest.raises(sqlite3.IntegrityError):
        add_constant(conn, key="载波频率", value="9.0Hz")
    assert get_constant(conn, "载波频率")["value"] == "7.83Hz"
    conn.close()


def test_location_neighbors(tmp_project):
    conn = get_connection(tmp_project)
    a = add_location(conn, name="中枢设施", loc_type="设施")
    b = add_location(conn, name="观测站", loc_type="设施")
    add_neighbor(conn, from_id=a, to_id=b, travel_days=3)
    assert [n["to_id"] for n in neighbors_of(conn, a)] == [b]
    conn.close()


def test_faction_self_parent_null_ok(tmp_project):
    conn = get_connection(tmp_project)
    fid = add_faction(conn, name="人族残部", ftype="阵营", stance="防御")
    sub = add_faction(conn, name="中枢守备", ftype="组织", stance="防御", parent_id=fid)
    assert sub is not None
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_worldbook.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 worldbook schema + 实现 repository**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS constants (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global' CHECK (scope IN ('global','volume-specific')),
    volume_id INTEGER,   -- scope=volume-specific 时关联
    source_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    loc_type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    parent_location_id INTEGER REFERENCES location(id)
);

CREATE TABLE IF NOT EXISTS location_neighbor (
    from_id INTEGER NOT NULL REFERENCES location(id),
    to_id INTEGER NOT NULL REFERENCES location(id),
    travel_days INTEGER,
    PRIMARY KEY(from_id, to_id)
);

CREATE TABLE IF NOT EXISTS time_period (
    label TEXT PRIMARY KEY,
    chapter_start INTEGER NOT NULL,
    chapter_end INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    CHECK (chapter_start <= chapter_end)
);

CREATE TABLE IF NOT EXISTS faction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    ftype TEXT NOT NULL DEFAULT '',
    stance TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    parent_faction_id INTEGER REFERENCES faction(id)
);

CREATE TABLE IF NOT EXISTS theme (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    evolution TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS motif (
    name TEXT PRIMARY KEY,
    meaning TEXT NOT NULL DEFAULT '',
    evolution TEXT NOT NULL DEFAULT ''
);
```

```python
# src/bedrock/repositories/worldbook.py
import sqlite3
from typing import Optional


def add_constant(conn, key, value, scope="global", volume_id=None, source_note=""):
    conn.execute(
        "INSERT INTO constants(key,value,scope,volume_id,source_note) VALUES(?,?,?,?,?)",
        (key, value, scope, volume_id, source_note))
    conn.commit()


def get_constant(conn, key):
    return conn.execute("SELECT * FROM constants WHERE key=?", (key,)).fetchone()


def list_constants(conn):
    return conn.execute("SELECT * FROM constants ORDER BY key").fetchall()


def add_location(conn, name, loc_type="", description="", state="", parent_location_id=None):
    cur = conn.execute(
        "INSERT INTO location(name,loc_type,description,state,parent_location_id) VALUES(?,?,?,?,?)",
        (name, loc_type, description, state, parent_location_id))
    conn.commit()
    return cur.lastrowid


def add_neighbor(conn, from_id, to_id, travel_days=None):
    conn.execute(
        "INSERT OR IGNORE INTO location_neighbor(from_id,to_id,travel_days) VALUES(?,?,?)",
        (from_id, to_id, travel_days))
    conn.commit()


def neighbors_of(conn, location_id):
    return conn.execute(
        "SELECT * FROM location_neighbor WHERE from_id=?", (location_id,)).fetchall()


def add_faction(conn, name, ftype="", stance="", state="", parent_faction_id=None):
    cur = conn.execute(
        "INSERT INTO faction(name,ftype,stance,state,parent_faction_id) VALUES(?,?,?,?,?)",
        (name, ftype, stance, state, parent_faction_id))
    conn.commit()
    return cur.lastrowid


def add_time_period(conn, label, chapter_start, chapter_end, description=""):
    conn.execute(
        "INSERT OR REPLACE INTO time_period(label,chapter_start,chapter_end,description) "
        "VALUES(?,?,?,?)", (label, chapter_start, chapter_end, description))
    conn.commit()


def add_theme(conn, name, description="", evolution=""):
    conn.execute(
        "INSERT OR REPLACE INTO theme(name,description,evolution) VALUES(?,?,?)",
        (name, description, evolution))
    conn.commit()


def add_motif(conn, name, meaning="", evolution=""):
    conn.execute(
        "INSERT OR REPLACE INTO motif(name,meaning,evolution) VALUES(?,?,?)",
        (name, meaning, evolution))
    conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_worldbook.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/worldbook.py tests/bedrock/test_worldbook.py
git commit -m "feat(bedrock): worldbook schema + repository (constants/locations/factions/themes/motifs)"
```

---

## Task 7: 悬链 Schema（状态机）+ 联结表 + Repository

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/suspense.py`
- Test: `tests/bedrock/test_suspense.py`

- [ ] **Step 1: 写失败测试（含状态机迁移校验）**

```python
# tests/bedrock/test_suspense.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.suspense import (
    plant_thread, record_consumption, get_thread, consumed_by_thread,
    IllegalTransition,
)


def _seed_beat(conn):
    from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")


def test_thread_lifecycle_and_consumption(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="书的来源", thread_type="mystery",
                       importance="high", planted_at_beat=b1, origin="scheduled",
                       planned_plant_volume=1, planned_resolve_volume=3)
    t = get_thread(conn, tid)
    assert t["status"] == "planted"

    # 在 b1 推进（planted→developing 合法）
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="developing", chapter=1)
    assert get_thread(conn, tid)["status"] == "developing"
    assert len(consumed_by_thread(conn, tid)) == 1
    conn.close()


def test_illegal_transition_rejected(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=b1, origin="emergent")
    # developing→planted 回退非法
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="developing", chapter=1)
    with pytest.raises(IllegalTransition):
        record_consumption(conn, thread_id=tid, beat_id=b1, new_status="planted", chapter=2)
    conn.close()


def test_resolved_implies_resolved_at_beat(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=b1, origin="emergent")
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="resolved", chapter=1)
    t = get_thread(conn, tid)
    assert t["status"] == "resolved"
    assert t["resolved_at_beat"] == b1
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_suspense.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 schema + 实现 repository**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS suspense_thread (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    thread_type TEXT NOT NULL CHECK (thread_type IN ('mystery','foreshadowing','character_arc','theme_arc','plot_arc')),
    importance TEXT NOT NULL CHECK (importance IN ('high','medium','low')),
    origin TEXT NOT NULL CHECK (origin IN ('scheduled','emergent')),
    status TEXT NOT NULL DEFAULT 'planted' CHECK (status IN ('scheduled','planted','developing','mature','partially_resolved','resolved','abandoned')),
    planted_at_beat INTEGER REFERENCES beat(id),
    resolved_at_beat INTEGER REFERENCES beat(id),
    planned_plant_volume INTEGER,
    planned_resolve_volume INTEGER
);
-- resolved 状态一致性：status=resolved 必有 resolved_at_beat（应用层 + 触发器双保险）
-- SQLite CHECK 无法跨列等价，用触发器：
CREATE TRIGGER IF NOT EXISTS trg_thread_resolved_beat
AFTER INSERT ON suspense_thread
WHEN NEW.status='resolved' AND NEW.resolved_at_beat IS NULL
BEGIN
    SELECT RAISE(ABORT, 'resolved status requires resolved_at_beat');
END;
CREATE TRIGGER IF NOT EXISTS trg_thread_resolved_beat_upd
AFTER UPDATE OF status ON suspense_thread
WHEN NEW.status='resolved' AND NEW.resolved_at_beat IS NULL
BEGIN
    SELECT RAISE(ABORT, 'resolved status requires resolved_at_beat');
END;

-- 悬链消费联结（单向 SSOT：thread 持有，beat 反查）
CREATE TABLE IF NOT EXISTS thread_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES suspense_thread(id),
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    new_status TEXT NOT NULL CHECK (new_status IN ('scheduled','planted','developing','mature','partially_resolved','resolved','abandoned')),
    chapter INTEGER NOT NULL,
    UNIQUE(thread_id, beat_id, new_status)
);

-- beat 种植声明（plant_threads）
CREATE TABLE IF NOT EXISTS thread_planting (
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    thread_id INTEGER NOT NULL REFERENCES suspense_thread(id),
    PRIMARY KEY(beat_id, thread_id)
);
```

```python
# src/bedrock/repositories/suspense.py
import sqlite3
from src.bedrock.enums import LEGAL_THREAD_TRANSITIONS, ThreadStatus


class IllegalTransition(Exception):
    pass


def plant_thread(conn, content, thread_type, importance, planted_at_beat,
                 origin, planned_plant_volume=None, planned_resolve_volume=None,
                 status="planted"):
    cur = conn.execute(
        "INSERT INTO suspense_thread(content,thread_type,importance,origin,status,"
        "planted_at_beat,planned_plant_volume,planned_resolve_volume) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (content, thread_type, importance, origin, status, planted_at_beat,
         planned_plant_volume, planned_resolve_volume))
    conn.commit()
    return cur.lastrowid


def get_thread(conn, thread_id):
    return conn.execute("SELECT * FROM suspense_thread WHERE id=?", (thread_id,)).fetchone()


def consumed_by_thread(conn, thread_id):
    """单向 SSOT：从 thread 反查哪些 beat 消费过它。"""
    return conn.execute(
        "SELECT * FROM thread_consumption WHERE thread_id=? ORDER BY chapter",
        (thread_id,)).fetchall()


def threads_advanced_at_beat(conn, beat_id):
    """beat 反查：这个 beat 推进了哪些悬链（派生视图，替代 beat.advance_threads）。"""
    return conn.execute(
        "SELECT thread_id, new_status FROM thread_consumption WHERE beat_id=?",
        (beat_id,)).fetchall()


def record_consumption(conn, thread_id, beat_id, new_status, chapter):
    """记录 beat 对悬链的消费（推进/回收）。校验状态机迁移合法性。"""
    prev_row = get_thread(conn, thread_id)
    if prev_row is None:
        raise ValueError(f"thread {thread_id} not found")
    prev = ThreadStatus(prev_row["status"])
    target = ThreadStatus(new_status)
    if target not in LEGAL_THREAD_TRANSITIONS.get(prev, set()):
        raise IllegalTransition(f"{prev.value}→{target.value} 非法迁移 (thread {thread_id})")

    resolved_beat = beat_id if target == ThreadStatus.RESOLVED else None
    # 落 thread_consumption（单向 SSOT）
    conn.execute(
        "INSERT OR IGNORE INTO thread_consumption(thread_id,beat_id,new_status,chapter) "
        "VALUES(?,?,?,?)", (thread_id, beat_id, new_status, chapter))
    # 更新 thread 状态（resolved 时写 resolved_at_beat）
    if target == ThreadStatus.RESOLVED:
        conn.execute(
            "UPDATE suspense_thread SET status=?, resolved_at_beat=? WHERE id=?",
            (new_status, resolved_beat, thread_id))
    else:
        conn.execute(
            "UPDATE suspense_thread SET status=? WHERE id=?", (new_status, thread_id))
    conn.commit()


def threads_planted_at_beat(conn, beat_id):
    return conn.execute(
        "SELECT thread_id FROM thread_planting WHERE beat_id=?", (beat_id,)).fetchall()


def declare_planting(conn, beat_id, thread_id):
    conn.execute(
        "INSERT OR IGNORE INTO thread_planting(beat_id,thread_id) VALUES(?,?)",
        (beat_id, thread_id))
    conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_suspense.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/suspense.py tests/bedrock/test_suspense.py
git commit -m "feat(bedrock): suspense schema (state machine) + consumption junction + repository"
```

---

## Task 8: Event Schema + 联结表 + Repository

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/event.py`
- Test: `tests/bedrock/test_event.py`

- [ ] **Step 1: 写失败测试（多次揭示）**

```python
# tests/bedrock/test_event.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.event import (
    create_event, add_reveal, reveal_beats_of, link_event_character,
    characters_in_event, add_cause,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat


def _two_beats(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    b1 = create_beat(conn, chapter_id=cid, sequence=1, purpose="第一个场景目的足够长")
    b2 = create_beat(conn, chapter_id=cid, sequence=2, purpose="第二个场景目的足够长")
    return b1, b2


def test_event_multiple_reveals(tmp_project):
    """Event 支持多次揭示（revealed_at_beats[]，避免 bitemporal 单区间丢失）。"""
    conn = get_connection(tmp_project)
    b1, b2 = _two_beats(conn)
    eid = create_event(conn, title="制造者真相", detail="代谢系统的本质",
                       chapter=1, volume=1, event_type="revelation")
    add_reveal(conn, event_id=eid, beat_id=b1)
    add_reveal(conn, event_id=eid, beat_id=b2)
    assert {r["beat_id"] for r in reveal_beats_of(conn, eid)} == {b1, b2}
    conn.close()


def test_event_characters_and_cause(tmp_project):
    conn = get_connection(tmp_project)
    from src.bedrock.repositories.character import create_character
    b1, b2 = _two_beats(conn)
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    e_cause = create_event(conn, title="起因", detail="d", chapter=1, volume=1, event_type="plot")
    e_eff = create_event(conn, title="结果", detail="d", chapter=2, volume=1, event_type="turning")
    link_event_character(conn, e_eff, c1)
    add_cause(conn, caused_event=e_eff, causing_event=e_cause)
    assert c1 in [r["character_id"] for r in characters_in_event(conn, e_eff)]
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_event.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 schema + 实现 repository**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    chapter INTEGER NOT NULL,
    volume INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('plot','turning','revelation','climax','gap','denouement')),
    is_gap INTEGER NOT NULL DEFAULT 0,
    gap_level INTEGER NOT NULL DEFAULT 0 CHECK (gap_level BETWEEN 0 AND 3),
    timeline_id TEXT
);

-- 多次揭示联结（Event ↔ Beat）
CREATE TABLE IF NOT EXISTS event_reveal (
    event_id INTEGER NOT NULL REFERENCES event(id),
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    PRIMARY KEY(event_id, beat_id)
);

CREATE TABLE IF NOT EXISTS event_character (
    event_id INTEGER NOT NULL REFERENCES event(id),
    character_id INTEGER NOT NULL REFERENCES character(id),
    PRIMARY KEY(event_id, character_id)
);

-- 因果链
CREATE TABLE IF NOT EXISTS event_cause (
    caused_event INTEGER NOT NULL REFERENCES event(id),
    causing_event INTEGER NOT NULL REFERENCES event(id),
    PRIMARY KEY(caused_event, causing_event)
);
```

```python
# src/bedrock/repositories/event.py
def create_event(conn, title, chapter, volume, event_type, detail="",
                 is_gap=False, gap_level=0, timeline_id=None):
    cur = conn.execute(
        "INSERT INTO event(title,detail,chapter,volume,event_type,is_gap,gap_level,timeline_id) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (title, detail, chapter, volume, event_type, int(is_gap), gap_level, timeline_id))
    conn.commit()
    return cur.lastrowid


def add_reveal(conn, event_id, beat_id):
    conn.execute(
        "INSERT OR IGNORE INTO event_reveal(event_id,beat_id) VALUES(?,?)",
        (event_id, beat_id))
    conn.commit()


def reveal_beats_of(conn, event_id):
    return conn.execute(
        "SELECT beat_id FROM event_reveal WHERE event_id=?", (event_id,)).fetchall()


def link_event_character(conn, event_id, character_id):
    conn.execute(
        "INSERT OR IGNORE INTO event_character(event_id,character_id) VALUES(?,?)",
        (event_id, character_id))
    conn.commit()


def characters_in_event(conn, event_id):
    return conn.execute(
        "SELECT character_id FROM event_character WHERE event_id=?", (event_id,)).fetchall()


def add_cause(conn, caused_event, causing_event):
    conn.execute(
        "INSERT OR IGNORE INTO event_cause(caused_event,causing_event) VALUES(?,?)",
        (caused_event, causing_event))
    conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_event.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/event.py tests/bedrock/test_event.py
git commit -m "feat(bedrock): event schema (multi-reveal) + junctions + repository"
```

---

## Task 9: Relation + Entity_State_Log（追加表）+ Amendment + ExportManifest

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/relation.py`
- Create: `src/bedrock/repositories/governance.py`
- Test: `tests/bedrock/test_relation_governance.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_relation_governance.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.relation import create_relation, append_state_log, state_log_of
from src.bedrock.repositories.governance import add_amendment, add_export_manifest
from src.bedrock.repositories.character import create_character


def test_relation_and_state_log(tmp_project):
    conn = get_connection(tmp_project)
    a = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    b = create_character(conn, name="韩峥", pronoun="他", role="supporting", gender="男")
    rid = create_relation(conn, from_id=a, to_id=b, rel_type="战友",
                          valid_from_chapter=1, current_state="信任")
    # 追加状态日志（immutable）
    append_state_log(conn, entity_type="relation", entity_id=rid, chapter=10,
                     field="current_state", old="信任", new="决裂", reason="背叛事件")
    log = state_log_of(conn, "relation", rid)
    assert len(log) == 1
    assert log[0]["new"] == "决裂"
    conn.close()


def test_amendment_and_export_manifest(tmp_project):
    conn = get_connection(tmp_project)
    aid = add_amendment(conn, entity_type="character", entity_id=1, chapter=5,
                        field="pronoun", old="它", new="祂", reason="T-1觉醒",
                        author="system")
    assert aid is not None
    eid = add_export_manifest(conn, scope="chapter", target_id=1, format="txt",
                              content_hash="abc", status="final")
    assert eid is not None
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_relation_governance.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 schema + 实现 repositories**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS relation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL REFERENCES character(id),
    to_id INTEGER NOT NULL REFERENCES character(id),
    rel_type TEXT NOT NULL,
    valid_from_chapter INTEGER,
    valid_to_chapter INTEGER,
    current_state TEXT NOT NULL DEFAULT '',
    CHECK (from_id <> to_id)
);

-- 通用追加日志（immutable）：location/faction/character/relation 的 state_history
CREATE TABLE IF NOT EXISTS entity_state_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('location','faction','character','relation')),
    entity_id INTEGER NOT NULL,
    chapter INTEGER NOT NULL,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT,
    reason TEXT NOT NULL DEFAULT ''
);

-- Amendment：跨实体修订留痕（append, immutable）
CREATE TABLE IF NOT EXISTS amendment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    chapter INTEGER,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL CHECK (author IN ('agent','human','system')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ExportManifest：导出清单/版本
CREATE TABLE IF NOT EXISTS export_manifest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK (scope IN ('chapter','volume','book')),
    target_id INTEGER,   -- chapter global_number / volume number / null for book
    format TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','final','published')),
    exported_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_snapshot TEXT NOT NULL DEFAULT '{}'   -- JSON
);
```

```python
# src/bedrock/repositories/relation.py
def create_relation(conn, from_id, to_id, rel_type, valid_from_chapter=None,
                    valid_to_chapter=None, current_state=""):
    cur = conn.execute(
        "INSERT INTO relation(from_id,to_id,rel_type,valid_from_chapter,valid_to_chapter,current_state) "
        "VALUES(?,?,?,?,?,?)",
        (from_id, to_id, rel_type, valid_from_chapter, valid_to_chapter, current_state))
    conn.commit()
    return cur.lastrowid


def append_state_log(conn, entity_type, entity_id, chapter, field, old, new, reason=""):
    """追加状态变更（immutable，只 INSERT 不 UPDATE）。"""
    cur = conn.execute(
        "INSERT INTO entity_state_log(entity_type,entity_id,chapter,field,old,new,reason) "
        "VALUES(?,?,?,?,?,?,?)",
        (entity_type, entity_id, chapter, field, old, new, reason))
    conn.commit()
    return cur.lastrowid


def state_log_of(conn, entity_type, entity_id):
    return conn.execute(
        "SELECT * FROM entity_state_log WHERE entity_type=? AND entity_id=? ORDER BY chapter, id",
        (entity_type, entity_id)).fetchall()
```

```python
# src/bedrock/repositories/governance.py
import json


def add_amendment(conn, entity_type, entity_id, field, new_value, old_value=None,
                  chapter=None, reason="", author="system"):
    cur = conn.execute(
        "INSERT INTO amendment(entity_type,entity_id,chapter,field,old_value,new_value,reason,author) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (entity_type, entity_id, chapter, field, old_value, new_value, reason, author))
    conn.commit()
    return cur.lastrowid


def add_export_manifest(conn, scope, format, content_hash, target_id=None,
                        status="draft", source_snapshot=None):
    cur = conn.execute(
        "INSERT INTO export_manifest(scope,target_id,format,content_hash,status,source_snapshot) "
        "VALUES(?,?,?,?,?,?)",
        (scope, target_id, format, content_hash, status,
         json.dumps(source_snapshot or {}, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_relation_governance.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/relation.py src/bedrock/repositories/governance.py tests/bedrock/test_relation_governance.py
git commit -m "feat(bedrock): relation + immutable state_log + amendment + export_manifest"
```

---

## Task 10: 大纲 Schema（VolumeOutline / MasterOutline）+ 灵感池

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/outline.py`
- Test: `tests/bedrock/test_outline.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_outline.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.outline import (
    save_volume_outline, get_volume_outline, lock_volume_outline,
    save_master_outline, get_master_outline,
    add_inspiration, consume_inspiration,
)
from src.bedrock.repositories.plot_tree import create_volume


def test_volume_outline_lock(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    save_volume_outline(conn, vid, beat_contracts=[{"chapter": 1, "beats": []}])
    assert get_volume_outline(conn, vid)["status"] == "drafted"
    lock_volume_outline(conn, vid)
    assert get_volume_outline(conn, vid)["status"] == "locked"
    conn.close()


def test_master_outline_single_row(tmp_project):
    conn = get_connection(tmp_project)
    save_master_outline(conn, key_milestones=[{"name": "觉醒", "expected_volume": 2}])
    mo = get_master_outline(conn)
    assert json.loads(mo["key_milestones"])[0]["name"] == "觉醒"
    # 再存覆盖同一行
    save_master_outline(conn, key_milestones=[{"name": "觉醒", "expected_volume": 3}])
    assert len(conn.execute("SELECT * FROM master_outline").fetchall()) == 1
    conn.close()


def test_inspiration_lifecycle(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="一个能听到城市电流声的主角", type="character")
    consume_inspiration(conn, iid, target_type="character", target_id=1)
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "consumed"
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_outline.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 schema + 实现 repository**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS volume_outline (
    volume_id INTEGER PRIMARY KEY REFERENCES volume(id),
    status TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN ('drafted','locked','writing','completed')),
    locked_at TEXT,
    beat_contracts TEXT NOT NULL DEFAULT '[]'   -- JSON: [{chapter, beats:[{purpose,...}]}]
);

CREATE TABLE IF NOT EXISTS master_outline (
    id INTEGER PRIMARY KEY CHECK (id = 1),   -- 单行
    volumes TEXT NOT NULL DEFAULT '[]',       -- JSON
    theme_evolution TEXT NOT NULL DEFAULT '',
    key_arcs TEXT NOT NULL DEFAULT '[]',      -- JSON
    key_milestones TEXT NOT NULL DEFAULT '[]', -- JSON
    rhythm_curve TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inspiration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('premise','scene','character','theme','mechanic','setting','twist')),
    status TEXT NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','refined','consumed','partial','discarded')),
    source TEXT NOT NULL DEFAULT '',
    consumed_into TEXT NOT NULL DEFAULT '[]',  -- JSON [{target_type,target_id}]
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    refined_at TEXT,
    promoted_at TEXT
);
```

```python
# src/bedrock/repositories/outline.py
import json


def save_volume_outline(conn, volume_id, beat_contracts):
    conn.execute(
        "INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) "
        "VALUES(?,COALESCE((SELECT status FROM volume_outline WHERE volume_id=?),'drafted'),?)",
        (volume_id, volume_id, json.dumps(beat_contracts, ensure_ascii=False)))
    conn.commit()


def get_volume_outline(conn, volume_id):
    return conn.execute(
        "SELECT * FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()


def lock_volume_outline(conn, volume_id):
    conn.execute(
        "UPDATE volume_outline SET status='locked', locked_at=datetime('now') WHERE volume_id=?",
        (volume_id,))
    conn.commit()


def save_master_outline(conn, volumes=None, theme_evolution=None, key_arcs=None,
                        key_milestones=None, rhythm_curve=None):
    fields = {}
    if volumes is not None: fields["volumes"] = json.dumps(volumes, ensure_ascii=False)
    if theme_evolution is not None: fields["theme_evolution"] = theme_evolution
    if key_arcs is not None: fields["key_arcs"] = json.dumps(key_arcs, ensure_ascii=False)
    if key_milestones is not None: fields["key_milestones"] = json.dumps(key_milestones, ensure_ascii=False)
    if rhythm_curve is not None: fields["rhythm_curve"] = rhythm_curve
    if not fields:
        return
    # 单行 upsert (id=1)
    conn.execute("INSERT OR IGNORE INTO master_outline(id) VALUES(1)")
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE master_outline SET {set_clause} WHERE id=1", tuple(fields.values()))
    conn.commit()


def get_master_outline(conn):
    return conn.execute("SELECT * FROM master_outline WHERE id=1").fetchone()


def add_inspiration(conn, content, type, source="", status="raw"):
    cur = conn.execute(
        "INSERT INTO inspiration(content,type,status,source) VALUES(?,?,?,?)",
        (content, type, status, source))
    conn.commit()
    return cur.lastrowid


def consume_inspiration(conn, inspiration_id, target_type, target_id):
    row = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    into = json.loads(row["consumed_into"]) if row and row["consumed_into"] else []
    into.append({"target_type": target_type, "target_id": target_id})
    conn.execute(
        "UPDATE inspiration SET status='consumed', consumed_into=? WHERE id=?",
        (json.dumps(into, ensure_ascii=False), inspiration_id))
    conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_outline.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/outline.py tests/bedrock/test_outline.py
git commit -m "feat(bedrock): outline schema (volume/master) + inspiration pool"
```

---

## Task 11: 遥测 Schema（ChapterMetrics / ChapterRuntime / StyleTemplate）+ Repository

**Files:**
- Modify: `src/bedrock/db/schema.sql`
- Create: `src/bedrock/repositories/telemetry.py`
- Test: `tests/bedrock/test_telemetry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_telemetry.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.telemetry import (
    write_chapter_metrics, get_chapter_metrics,
    record_agent_invocation, record_llm_call, get_chapter_runtime,
    save_style_template,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed_chapter(conn, gnum=1):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    return create_chapter(conn, volume_id=vid, global_number=gnum, title="t")


def test_chapter_metrics_always_system_recomputed(tmp_project):
    conn = get_connection(tmp_project)
    cid = _seed_chapter(conn)
    write_chapter_metrics(conn, chapter_id=cid, word_count=4463,
                          grep_metrics={"notXisY": 2, "dash": 1, "period": 22},
                          threads_consumed=3, consumption_balance=1.5,
                          beat_yield_rate=1.0)
    m = get_chapter_metrics(conn, cid)
    assert m["source"] == "system_recomputed"
    assert m["word_count"] == 4463
    conn.close()


def test_chapter_runtime_records_blackwall_and_llm(tmp_project):
    conn = get_connection(tmp_project)
    cid = _seed_chapter(conn)
    rid = record_agent_invocation(conn, chapter_id=cid, agent_type="chapter_writer",
                                  black_wall_ms=300000)
    record_llm_call(conn, runtime_id=rid, phase="writing", model="claude-opus",
                    prompt_tokens=20000, completion_tokens=8000, duration_ms=295000)
    rt = get_chapter_runtime(conn, cid)
    assert rt["total_black_wall_ms"] == 300000
    assert rt["llm_tokens"] == 28000
    conn.close()


def test_style_template_roundtrip(tmp_project):
    conn = get_connection(tmp_project)
    sid = save_style_template(conn, fingerprint={"sentence_length_mean": 18.5},
                              sample_chapters=[1, 2, 3])
    assert sid is not None
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_telemetry.py -v`
Expected: FAIL（`no such table`）

- [ ] **Step 3: 追加 schema + 实现 repository**

```sql
-- 追加到 schema.sql

CREATE TABLE IF NOT EXISTS chapter_metrics (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapter(id),
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    word_count INTEGER,
    sentence_length_stats TEXT NOT NULL DEFAULT '{}',  -- JSON
    grep_metrics TEXT NOT NULL DEFAULT '{}',           -- JSON {notXisY,dash,period}
    sensory_density REAL,
    dialogue_ratio REAL,
    threads_consumed REAL,
    consumption_balance REAL,
    beat_yield_rate REAL,
    declared_json TEXT NOT NULL DEFAULT '{}',          -- advisory: agent 自报存档不消费
    source TEXT NOT NULL DEFAULT 'system_recomputed' CHECK (source='system_recomputed')
);

CREATE TABLE IF NOT EXISTS chapter_runtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapter(id),
    session_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    version TEXT,
    total_black_wall_ms INTEGER NOT NULL DEFAULT 0,
    tool_count INTEGER NOT NULL DEFAULT 0,
    llm_tokens INTEGER NOT NULL DEFAULT 0,
    llm_call_count INTEGER NOT NULL DEFAULT 0,
    editing_rounds INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_invocation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runtime_id INTEGER NOT NULL REFERENCES chapter_runtime(id),
    agent_type TEXT NOT NULL,
    start_ts TEXT,
    end_ts TEXT,
    black_wall_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_call (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runtime_id INTEGER NOT NULL REFERENCES chapter_runtime(id),
    phase TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tool_call (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runtime_id INTEGER NOT NULL REFERENCES chapter_runtime(id),
    tool TEXT NOT NULL,
    duration_ms REAL,
    error TEXT,
    decision TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS style_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_works TEXT NOT NULL DEFAULT '[]',
    sample_chapters TEXT NOT NULL DEFAULT '[]',
    extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
    fingerprint TEXT NOT NULL DEFAULT '{}'   -- JSON
);
```

```python
# src/bedrock/repositories/telemetry.py
import json


def write_chapter_metrics(conn, chapter_id, word_count=None, sentence_length_stats=None,
                          grep_metrics=None, sensory_density=None, dialogue_ratio=None,
                          threads_consumed=None, consumption_balance=None,
                          beat_yield_rate=None, declared=None):
    """authoritative 写入——source 永远 system_recomputed。declared 进 declared_json（advisory）。"""
    conn.execute(
        "INSERT OR REPLACE INTO chapter_metrics("
        "chapter_id,word_count,sentence_length_stats,grep_metrics,sensory_density,"
        "dialogue_ratio,threads_consumed,consumption_balance,beat_yield_rate,declared_json,source) "
        "VALUES(?,?,?,?,?,?,?,?,?,?, 'system_recomputed')",
        (chapter_id, word_count,
         json.dumps(sentence_length_stats or {}, ensure_ascii=False),
         json.dumps(grep_metrics or {}, ensure_ascii=False),
         sensory_density, dialogue_ratio, threads_consumed, consumption_balance,
         beat_yield_rate, json.dumps(declared or {}, ensure_ascii=False)))
    conn.commit()


def get_chapter_metrics(conn, chapter_id):
    return conn.execute("SELECT * FROM chapter_metrics WHERE chapter_id=?",
                        (chapter_id,)).fetchone()


def _create_runtime(conn, chapter_id, session_id=None, version=None, editing_rounds=0):
    cur = conn.execute(
        "INSERT INTO chapter_runtime(chapter_id,session_id,version,editing_rounds) "
        "VALUES(?,?,?,?)", (chapter_id, session_id, version, editing_rounds))
    conn.commit()
    return cur.lastrowid


def record_agent_invocation(conn, chapter_id, agent_type, black_wall_ms,
                            start_ts=None, end_ts=None, session_id=None, version=None):
    rid = _create_runtime(conn, chapter_id, session_id, version)
    conn.execute(
        "INSERT INTO agent_invocation(runtime_id,agent_type,start_ts,end_ts,black_wall_ms) "
        "VALUES(?,?,?,?,?)", (rid, agent_type, start_ts, end_ts, black_wall_ms))
    conn.execute(
        "UPDATE chapter_runtime SET total_black_wall_ms=total_black_wall_ms+? WHERE id=?",
        (black_wall_ms, rid))
    conn.commit()
    return rid


def record_llm_call(conn, runtime_id, phase, model, prompt_tokens, completion_tokens, duration_ms):
    conn.execute(
        "INSERT INTO llm_call(runtime_id,phase,model,prompt_tokens,completion_tokens,duration_ms) "
        "VALUES(?,?,?,?,?,?)", (runtime_id, phase, model, prompt_tokens, completion_tokens, duration_ms))
    conn.execute(
        "UPDATE chapter_runtime SET llm_tokens=llm_tokens+?, llm_call_count=llm_call_count+1 WHERE id=?",
        (prompt_tokens + completion_tokens, runtime_id))
    conn.commit()


def get_chapter_runtime(conn, chapter_id):
    return conn.execute(
        "SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
        (chapter_id,)).fetchone()


def save_style_template(conn, fingerprint, source_works=None, sample_chapters=None):
    cur = conn.execute(
        "INSERT INTO style_template(source_works,sample_chapters,fingerprint) VALUES(?,?,?)",
        (json.dumps(source_works or [], ensure_ascii=False),
         json.dumps(sample_chapters or [], ensure_ascii=False),
         json.dumps(fingerprint, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_telemetry.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/db/schema.sql src/bedrock/repositories/telemetry.py tests/bedrock/test_telemetry.py
git commit -m "feat(bedrock): telemetry schema (metrics/runtime/style_template) + repository"
```

---

## Task 12: 跨字段校验（Python Validators，补 SQLite CHECK 表达不了的）

**Files:**
- Create: `src/bedrock/validation.py`
- Test: `tests/bedrock/test_validation.py`

> 校验对象：pronoun-gender 一致性、narrative 段必挂 beat（已在 CHECK 但提供应用层明确报错）、resolved↔resolved_at_beat（触发器兜底但应用层校验更清晰）、悬链状态机迁移（已在 repo，这里汇总）、faction/location 树环检测。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_validation.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.validation import (
    validate_pronoun_gender_consistency, ValidationError, detect_cycle,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_faction


def test_pronoun_gender_mismatch_caught(tmp_project):
    """gender=男 但 pronoun=她 应被应用层校验拦截（CHECK 表达不了跨列语义）。"""
    conn = get_connection(tmp_project)
    # 直接 SQL 绕过 repo 插入一个不一致行
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) "
                 "VALUES('X','她','男','minor','active')")
    with pytest.raises(ValidationError):
        validate_pronoun_gender_consistency(conn)
    conn.close()


def test_faction_cycle_detected(tmp_project):
    conn = get_connection(tmp_project)
    a = add_faction(conn, name="A")
    b = add_faction(conn, name="B", parent_id=a)
    conn.execute("UPDATE faction SET parent_faction_id=? WHERE id=?", (b, a))
    conn.commit()
    with pytest.raises(ValidationError):
        detect_cycle(conn, "faction")
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_validation.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 validation.py**

```python
# src/bedrock/validation.py
import sqlite3


class ValidationError(Exception):
    pass


_PRONOUN_GENDER = {
    "他": {"男"},
    "她": {"女"},
    "它": {"无", "未知", "其他"},
    "祂": {"无", "未知", "其他"},
    "TA": {"男", "女", "无", "未知", "其他"},   # 中性，任意
}


def validate_pronoun_gender_consistency(conn: sqlite3.Connection) -> None:
    """gender 非 null 时，必须与 pronoun 语义一致。gender=未知 豁免。"""
    rows = conn.execute(
        "SELECT id, name, pronoun, gender FROM character WHERE gender IS NOT NULL AND gender != '未知'"
    ).fetchall()
    for r in rows:
        allowed = _PRONOUN_GENDER.get(r["pronoun"], set())
        if r["gender"] not in allowed:
            raise ValidationError(
                f"character {r['name']}(id={r['id']}): pronoun={r['pronoun']} 与 gender={r['gender']} 不一致")


def detect_cycle(conn: sqlite3.Connection, entity: str) -> None:
    """检测 faction/location 的 parent 自引用环。"""
    table = entity  # 'faction' or 'location'
    col = f"parent_{entity}_id"
    rows = conn.execute(f"SELECT id, {col} FROM {table}").fetchall()
    parent_of = {r["id"]: r[col] for r in rows}
    for start in parent_of:
        seen = set()
        cur = start
        while cur is not None:
            if cur in seen:
                raise ValidationError(f"{entity} 出现环：起点 id={start}")
            seen.add(cur)
            cur = parent_of.get(cur)
    # None


def validate_resolved_thread_consistency(conn: sqlite3.Connection) -> None:
    """resolved 状态必须有 resolved_at_beat（触发器兜底，这里二次校验）。"""
    rows = conn.execute(
        "SELECT id FROM suspense_thread WHERE status='resolved' AND resolved_at_beat IS NULL"
    ).fetchall()
    if rows:
        raise ValidationError(f"{len(rows)} 条悬链 status=resolved 但缺 resolved_at_beat")


def validate_all(conn: sqlite3.Connection) -> list[str]:
    """跑全部跨字段校验，返回问题列表（不抛异常，便于聚合报告）。"""
    issues = []
    for fn in (validate_pronoun_gender_consistency,):
        try:
            fn(conn)
        except ValidationError as e:
            issues.append(str(e))
    try:
        detect_cycle(conn, "faction")
    except ValidationError as e:
        issues.append(str(e))
    try:
        detect_cycle(conn, "location")
    except ValidationError as e:
        issues.append(str(e))
    try:
        validate_resolved_thread_consistency(conn)
    except ValidationError as e:
        issues.append(str(e))
    return issues
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_validation.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/validation.py tests/bedrock/test_validation.py
git commit -m "feat(bedrock): cross-field validators (pronoun-gender, tree cycles, resolved-beat)"
```

---

## Task 13: 新作品初始化 + CLI 入口 + 集成冒烟测试

**Files:**
- Create: `src/bedrock/init_project.py`
- Create: `src/bedrock/__main__.py`
- Test: `tests/bedrock/test_init_project.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_init_project.py
import subprocess
import sys
from pathlib import Path
from src.bedrock.init_project import init_project
from src.bedrock.db.connection import get_connection


def test_init_creates_empty_db_with_full_schema(tmp_path):
    proj = tmp_path / "new_novel"
    init_project(proj, work_name="测试作品")
    assert (proj / "bedrock.db").exists()
    # 所有表都在
    conn = get_connection(proj)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"schema_version", "volume", "chapter", "beat", "paragraph",
                "character", "character_secret", "character_knowledge",
                "pronoun_override", "character_faction", "constants", "location",
                "location_neighbor", "time_period", "faction", "theme", "motif",
                "suspense_thread", "thread_consumption", "thread_planting",
                "event", "event_reveal", "event_character", "event_cause",
                "relation", "entity_state_log", "amendment", "export_manifest",
                "volume_outline", "master_outline", "inspiration",
                "chapter_metrics", "chapter_runtime", "agent_invocation",
                "llm_call", "tool_call", "style_template"}
    missing = expected - tables
    assert not missing, f"缺表: {missing}"
    conn.close()


def test_init_refuses_existing_db_without_force(tmp_path):
    proj = tmp_path / "n"
    init_project(proj, work_name="x")
    import pytest
    with pytest.raises(FileExistsError):
        init_project(proj, work_name="x")
    # force 可覆盖
    init_project(proj, work_name="x", force=True)


def test_cli_init_smoke(tmp_path):
    """CLI 入口可调用：python -m src.bedrock init <path> --name X"""
    proj = tmp_path / "cli_novel"
    result = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "init", str(proj), "--name", "CLI作品"],
        capture_output=True, text=True, cwd=Path.cwd())
    assert result.returncode == 0, result.stderr
    assert (proj / "bedrock.db").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_init_project.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 init_project.py**

```python
# src/bedrock/init_project.py
from pathlib import Path
from src.bedrock.db.migrate import apply_migrations


def init_project(project_dir: Path, work_name: str, force: bool = False) -> None:
    """初始化新作品项目：建目录 + 空白 DB（全 schema）。不迁移历史数据。"""
    project_dir = Path(project_dir)
    db_path = project_dir / "bedrock.db"
    if db_path.exists() and not force:
        raise FileExistsError(f"{db_path} 已存在；传 force=True 覆盖")
    project_dir.mkdir(parents=True, exist_ok=True)
    apply_migrations(project_dir)
    # 记录作品名到 constants（作品级元数据）
    from src.bedrock.db.connection import get_connection
    from src.bedrock.repositories.worldbook import add_constant
    conn = get_connection(project_dir)
    try:
        add_constant(conn, key="work_name", value=work_name, source_note="init_project")
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: 实现 __main__.py（CLI 入口）**

```python
# src/bedrock/__main__.py
import argparse
from pathlib import Path
from src.bedrock.init_project import init_project


def main():
    parser = argparse.ArgumentParser(prog="bedrock", description="V3 小说管线 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="初始化新作品项目")
    p_init.add_argument("path", type=Path)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.cmd == "init":
        init_project(args.path, work_name=args.name, force=args.force)
        print(f"已初始化作品 '{args.name}' 于 {args.path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_init_project.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 跑全量测试**

Run: `python -m pytest tests/bedrock/ -v`
Expected: 全部 PASS（~25 tests）

- [ ] **Step 7: Commit**

```bash
git add src/bedrock/init_project.py src/bedrock/__main__.py tests/bedrock/test_init_project.py
git commit -m "feat(bedrock): project init + CLI entrypoint + integration smoke test"
```

---

## Self-Review 自检

**1. Spec 覆盖：** spec §3 各实体 → 任务映射：
- §3.1 剧情树+段落 → Task 2,3
- §3.2 大纲三层 → Task 10（volume_outline/master_outline；beat 契约的运行时校验属后续 SP，schema 已存 beat_contracts JSON）
- §3.3 悬链 → Task 7
- §3.4 Worldbook → Task 6
- §3.5 角色+关系+可见性 → Task 4,5,9
- §3.6 Event → Task 8（Dialogue 不独立成实体，已移除）
- §3.7 联结表 → 散布在各 Task（beat_character 待补——见下）
- §3.8 灵感池 → Task 10
- §3.9 正文+导出 → Task 2,3（paragraph）+ Task 9（ExportManifest）；导出组装逻辑属后续 SP
- §3.10 机制层实体 → Task 11
- §3.11 bitemporal → schema 存 story_time/timeline_id（Task 2），校验归后续 SP

**发现一个缺口：** `beat_character` 联结表（beat.participating_characters[]）未在任何 Task 建表。需补。

**2. 修复缺口 — 在 Task 8 后补 beat_character：** 已知缺口，执行计划时在 Task 7 或 8 附带加入 schema.sql + 一个 repo 函数（`link_beat_character(beat_id, character_id, role)` / `characters_in_beat(beat_id)`）。schema DDL：
```sql
CREATE TABLE IF NOT EXISTS beat_character (
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    character_id INTEGER NOT NULL REFERENCES character(id),
    role TEXT NOT NULL DEFAULT '',   -- 该角色在此 beat 的参与角色（视角/在场/提及）
    PRIMARY KEY(beat_id, character_id, role)
);
```
此 DDL 追加到 Task 8 的 schema 步骤，repo 函数追加到 `repositories/event.py` 或新建 `repositories/beat_link.py`。

**3. Placeholder 扫描：** 无 TBD/TODO；所有步骤含完整代码与命令。

**4. 类型/签名一致性：** repository 函数签名跨任务一致（均接收 `conn` 为首参，返回 `lastrowid` 或 `Row`）。`record_consumption` 抛 `IllegalTransition`（Task 7 定义，测试用同）。`validate_pronoun_gender_consistency` 抛 `ValidationError`（Task 12 定义）。

**5. 业务逻辑剥离确认：** SP1 不含 beat 兑现校验逻辑、L2 重算、agent 编排、导出文件组装、StyleTemplate 提取——这些属后续 SP。SP1 只交付：schema + CRUD + 跨字段校验 + 初始化。

---

## 执行交接

计划完成，保存于 `docs/superpowers/plans/2026-06-14-novel-v3-sp1-data-skeleton.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每个 Task 派新子代理，任务间 review，迭代快

**2. Inline Execution** — 当前会话用 executing-plans 批量执行 + checkpoint

选哪种？
