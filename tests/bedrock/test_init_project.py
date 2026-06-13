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
                "llm_call", "tool_call", "style_template", "beat_character"}
    missing = expected - tables
    assert not missing, f"缺表: {missing}"
    conn.close()


def test_init_refuses_existing_db_without_force(tmp_path):
    proj = tmp_path / "n"
    init_project(proj, work_name="x")
    import pytest
    with pytest.raises(FileExistsError):
        init_project(proj, work_name="x")
    init_project(proj, work_name="x", force=True)


def test_cli_init_smoke(tmp_path):
    proj = tmp_path / "cli_novel"
    result = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "init", str(proj), "--name", "CLI作品"],
        capture_output=True, text=True, cwd=Path.cwd())
    assert result.returncode == 0, result.stderr
    assert (proj / "bedrock.db").exists()
