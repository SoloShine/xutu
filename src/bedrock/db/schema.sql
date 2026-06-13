-- src/bedrock/db/schema.sql
-- V3 数据骨架 schema（代号磐石 Bedrock）。逐步追加（后续 Task 往此文件追加 DDL）。

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    chapter_start INTEGER NOT NULL,
    chapter_end INTEGER NOT NULL,
    volume_type TEXT NOT NULL CHECK (volume_type IN ('opening','advancing','climax','epilogue','multi-pov')),
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','writing','completed','archived')),
    theme_seeds TEXT NOT NULL DEFAULT '[]',
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
    pov_character_id INTEGER,
    scene_setting TEXT NOT NULL DEFAULT '{}',
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
    CHECK (beat_id IS NOT NULL OR role IN ('transition','ambient','narration'))
);

CREATE TABLE IF NOT EXISTS character (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    aliases TEXT NOT NULL DEFAULT '[]',
    pronoun TEXT NOT NULL CHECK (pronoun IN ('他','她','它','祂','TA')),
    gender TEXT CHECK (gender IS NULL OR gender IN ('男','女','无','未知','其他')),
    role TEXT NOT NULL CHECK (role IN ('protagonist','supporting','antagonist','minor')),
    faction_id INTEGER,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','dormant','deceased','ascended','merged')),
    personality TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    abilities TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS character_secret (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    vis_mode TEXT NOT NULL CHECK (vis_mode IN ('public','secret_until','faction','characters')),
    vis_ref TEXT NOT NULL DEFAULT '{}',
    vis_axis TEXT NOT NULL CHECK (vis_axis IN ('character_epistemic','reader_disclosure')),
    UNIQUE(character_id, key, vis_axis)
);

CREATE TABLE IF NOT EXISTS character_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    fact_id TEXT NOT NULL,
    learned_at_beat INTEGER,
    confidence REAL NOT NULL DEFAULT 1.0,
    decay REAL NOT NULL DEFAULT 0.0,
    UNIQUE(character_id, fact_id)
);

CREATE TABLE IF NOT EXISTS pronoun_override (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character(id),
    from_chapter INTEGER NOT NULL,
    pronoun TEXT NOT NULL CHECK (pronoun IN ('他','她','它','祂','TA')),
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_faction (
    character_id INTEGER NOT NULL REFERENCES character(id),
    faction_id INTEGER NOT NULL,
    period_start INTEGER,
    period_end INTEGER,
    PRIMARY KEY(character_id, faction_id, period_start)
);


-- ===== Worldbook (Task 6) =====

CREATE TABLE IF NOT EXISTS constants (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global' CHECK (scope IN ('global','volume-specific')),
    volume_id INTEGER,
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


-- ===== Suspense threads (Task 7) =====

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

CREATE TABLE IF NOT EXISTS thread_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES suspense_thread(id),
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    new_status TEXT NOT NULL CHECK (new_status IN ('scheduled','planted','developing','mature','partially_resolved','resolved','abandoned')),
    chapter INTEGER NOT NULL,
    UNIQUE(thread_id, beat_id, new_status)
);

CREATE TABLE IF NOT EXISTS thread_planting (
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    thread_id INTEGER NOT NULL REFERENCES suspense_thread(id),
    PRIMARY KEY(beat_id, thread_id)
);


-- ===== Event (Task 8) =====

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

CREATE TABLE IF NOT EXISTS event_cause (
    caused_event INTEGER NOT NULL REFERENCES event(id),
    causing_event INTEGER NOT NULL REFERENCES event(id),
    PRIMARY KEY(caused_event, causing_event)
);


-- ===== Relation + Entity_State_Log + Governance (Task 9) =====

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

CREATE TABLE IF NOT EXISTS export_manifest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK (scope IN ('chapter','volume','book')),
    target_id INTEGER,
    format TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','final','published')),
    exported_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_snapshot TEXT NOT NULL DEFAULT '{}'
);
