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
