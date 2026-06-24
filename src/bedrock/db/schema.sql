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
    pov_character_id INTEGER REFERENCES character(id),
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
    faction_id INTEGER REFERENCES faction(id),
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
    volume_id INTEGER REFERENCES volume(id),
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


-- ===== Outline (Volume/Master) + Inspiration pool (Task 10) =====

CREATE TABLE IF NOT EXISTS volume_outline (
    volume_id INTEGER PRIMARY KEY REFERENCES volume(id),
    status TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN ('drafted','locked','writing','completed')),
    locked_at TEXT,
    beat_contracts TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS master_outline (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    volumes TEXT NOT NULL DEFAULT '[]',
    theme_evolution TEXT NOT NULL DEFAULT '',
    key_arcs TEXT NOT NULL DEFAULT '[]',
    key_milestones TEXT NOT NULL DEFAULT '[]',
    rhythm_curve TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inspiration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('premise','scene','character','theme','mechanic','setting','twist')),
    status TEXT NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','refined','consumed','partial','discarded')),
    source TEXT NOT NULL DEFAULT '',
    consumed_into TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    refined_at TEXT,
    promoted_at TEXT
);

CREATE TABLE IF NOT EXISTS chapter_metrics (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapter(id),
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    word_count INTEGER,
    sentence_length_stats TEXT NOT NULL DEFAULT '{}',
    grep_metrics TEXT NOT NULL DEFAULT '{}',
    sensory_density REAL,
    dialogue_ratio REAL,
    threads_consumed REAL,
    consumption_balance REAL,
    beat_yield_rate REAL,
    declared_json TEXT NOT NULL DEFAULT '{}',
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
    fingerprint TEXT NOT NULL DEFAULT '{}',
    scope TEXT NOT NULL DEFAULT 'work',
    volume_id INTEGER,
    directive TEXT NOT NULL DEFAULT '',
    word_count_target TEXT NOT NULL DEFAULT '[3000,5000]',
    max_edit_rounds INTEGER NOT NULL DEFAULT 3,
    hygiene TEXT NOT NULL DEFAULT '{}',
    enabled_dims TEXT NOT NULL DEFAULT '[]',
    scalar_targets TEXT NOT NULL DEFAULT '{}',
    reference_sample TEXT NOT NULL DEFAULT '',
    directive_source TEXT NOT NULL DEFAULT '',
    style_examples TEXT NOT NULL DEFAULT '{}'   -- {good:[str], bad:[str]} 作者策划的正反例,注入 writer【风格示范】
);


-- ===== 文风实测缓存(章写完刷新,工作台读缓存,免每次全量重算) =====
CREATE TABLE IF NOT EXISTS style_actual_cache (
    scope TEXT NOT NULL DEFAULT 'work',
    volume_id INTEGER,
    fingerprint TEXT NOT NULL DEFAULT '{}',
    scalars TEXT NOT NULL DEFAULT '{}',
    chapter_count INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (scope, volume_id)
);


-- ===== Beat <-> Character junction (Task 13 / SP1 gap) =====

CREATE TABLE IF NOT EXISTS beat_character (
    beat_id INTEGER NOT NULL REFERENCES beat(id),
    character_id INTEGER NOT NULL REFERENCES character(id),
    role TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(beat_id, character_id, role)
);


-- ===== SP4 抗博弈管线：诊断标记（SP5 VolumeReview 消费）=====
CREATE TABLE IF NOT EXISTS chapter_review_flag (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapter(id),
    l2_unresolved INTEGER NOT NULL DEFAULT 0,
    persisted_violations TEXT NOT NULL DEFAULT '[]',
    likely_rule_or_model_issue INTEGER NOT NULL DEFAULT 0,
    polish_broke_beat INTEGER NOT NULL DEFAULT 0,
    forced_persist_failed INTEGER NOT NULL DEFAULT 0,
    advisory_drift TEXT NOT NULL DEFAULT '{}',
    flagged_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ===== SP5 治理层：卷级 watchdog 发现（卷间 BLOCKING 门禁）=====
CREATE TABLE IF NOT EXISTS volume_review (
    volume_id INTEGER PRIMARY KEY REFERENCES volume(id),
    watchdog_findings TEXT NOT NULL DEFAULT '{}',
    blocking INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ===== 编排旋钮配置（runner-agnostic；phase 1 冻结自 .js 硬编码快照）=====
-- 与 style_template 同范式：scope=work|volume + 字段级 merge + upsert 不覆盖。
-- 只装编排旋钮（caps/模型/阶段开关/prompt 路径），文风项已在 style_template（RC3 单真相源）。
-- 消费方：LangGraph runner（经 CLI get-workflow-config 读）；当前 .js 不读（保持现状）。
CREATE TABLE IF NOT EXISTS workflow_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL DEFAULT 'work',        -- work | volume
    volume_id INTEGER,                          -- 仅 scope=volume 有值
    caps TEXT NOT NULL DEFAULT '{}',            -- {writer,editor,repair,style,vr_fix} 迭代上限
    models TEXT NOT NULL DEFAULT '{}',          -- {各agent: 模型名|null=runner默认}
    phases TEXT NOT NULL DEFAULT '{}',          -- {polish:auto|on|off, consistency:bool, ...}
    prompts TEXT NOT NULL DEFAULT '{}',         -- {writer/editor/volume_review: .md 路径}
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ===== 工作流运行事件（phase 2 实时可观测性）=====
-- runner（当前 .js / 将来 LangGraph）边跑边写;Web 面板 Vue Flow 只读图轮询渲染。
-- 纯遥测旁路:不影响 L2/verify-persisted 信任锚,不进控制流判决。
CREATE TABLE IF NOT EXISTS workflow_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_global INTEGER,                     -- 本章 global_number;volume 级 run 可空
    volume_id INTEGER,
    runner TEXT NOT NULL DEFAULT 'js',          -- js | langgraph（谁发射的）
    status TEXT NOT NULL DEFAULT 'running',     -- running | completed | failed | aborted
    current_node TEXT NOT NULL DEFAULT '',      -- 最近报告的节点/阶段
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS workflow_run_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES workflow_run(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,                        -- run 内单调（1-based）
    node TEXT NOT NULL,                          -- boot/write/revise/consistency/finalize/l2/...
    kind TEXT NOT NULL,                          -- start|enter|iteration|l2_verdict|commit|error|end
    payload TEXT NOT NULL DEFAULT '{}',          -- JSON: {iterations, verdict, word_count, detail, ...}
    ts TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ===== LLM 连接配置（runner 经 API 调模型;作者控制台可配）=====
-- 项目级单行(id 锁=1):provider/base_url/api_key/default_model。
-- base_url 支持第三方/代理(network);api_key 存 DB(本地作者工具),env 兜底。GET 掩码不回全文。
CREATE TABLE IF NOT EXISTS llm_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL DEFAULT 'anthropic',   -- anthropic|openai|...
    base_url TEXT NOT NULL DEFAULT '',             -- 空=官方端点;非空=第三方/代理
    api_key TEXT NOT NULL DEFAULT '',              -- 空=读 env(ANTHROPIC_API_KEY 等)兜底
    default_model TEXT NOT NULL DEFAULT '',        -- 空=llm.py 内置默认;覆盖 workflow_config.models
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ===== 作者助手 agent(对话式 AI 工作台)=====
-- chat_session:一个作品可有多个会话(各话题);chat_message:对话历史;
-- chat_proposal:agent 产的结构化提案(作者审批后才落库经 repo 函数,守铁律)。
CREATE TABLE IF NOT EXISTS chat_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                           -- user | assistant | tool
    content TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chat_proposal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,                    -- create_chapter_with_beat | trigger_run | ...
    payload TEXT NOT NULL DEFAULT '{}',           -- JSON,对齐实体 schema
    status TEXT NOT NULL DEFAULT 'pending',       -- pending | approved | rejected
    result TEXT,                                  -- 审批后执行结果(JSON 或错误)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at TEXT
);
