# tests/bedrock/test_repo_character.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.character import (
    create_character, get_character, add_secret,
    visible_secrets_for_context, set_pronoun_override,
    add_knowledge, knowledge_of,
)


def _seed_factionless_char(conn, name, pronoun="他", gender="男"):
    return create_character(conn, name=name, pronoun=pronoun, gender=gender,
                            role="protagonist", state="active")


def test_visible_secrets_filters_by_chapter_and_pov(tmp_project):
    conn = get_connection(tmp_project)
    a = _seed_factionless_char(conn, "林深", "他", "男")
    b = _seed_factionless_char(conn, "拾", "她", "女")
    add_secret(conn, a, key="真实性别", value="女",
               vis_mode="secret_until", vis_ref={"reveal_chapter": 50},
               vis_axis="reader_disclosure")
    add_secret(conn, a, key="卧底身份", value="反派卧底",
               vis_mode="characters", vis_ref={"character_ids": [b]},
               vis_axis="character_epistemic")
    add_secret(conn, a, key="公开过往", value="曾入伍",
               vis_mode="public", vis_ref={},
               vis_axis="reader_disclosure")

    ep_seen = visible_secrets_for_context(conn, a, chapter=10, pov_character_id=b,
                                          axis="character_epistemic")
    keys_ep = {s["key"] for s in ep_seen}
    assert "卧底身份" in keys_ep
    assert "真实性别" not in keys_ep

    rd_seen = visible_secrets_for_context(conn, a, chapter=60, pov_character_id=b,
                                          axis="reader_disclosure")
    keys_rd = {s["key"] for s in rd_seen}
    assert "真实性别" in keys_rd
    assert "公开过往" in keys_rd
    conn.close()


def test_character_knowledge_roundtrip(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    add_knowledge(conn, cid, fact_id="代谢系统真相", learned_at_beat=5, confidence=0.8)
    ks = knowledge_of(conn, cid)
    assert len(ks) == 1
    assert ks[0]["fact_id"] == "代谢系统真相"
    assert ks[0]["confidence"] == 0.8
    conn.close()
