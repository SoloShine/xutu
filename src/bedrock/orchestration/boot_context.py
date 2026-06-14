# src/bedrock/orchestration/boot_context.py
"""装配子代理启动上下文：beat 契约 + reader-disclosed secrets + StyleTemplate 指纹 + constants。"""
from src.bedrock.repositories.plot_tree import list_beats_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.style.template_repo import get_effective_fingerprint


def _reader_disclosed_secrets(conn):
    """只取 reader_disclosure 轴 + public vis_mode 的 secret（不泄露 secret_until/faction）。"""
    rows = conn.execute(
        "SELECT character_id, key, value FROM character_secret "
        "WHERE vis_axis='reader_disclosure' AND vis_mode='public'").fetchall()
    return [dict(r) for r in rows]


def get_chapter_boot_context(conn, chapter_id, volume_id):
    """返回 {beat_contracts, reader_disclosed_secrets, fingerprint, constants}。"""
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)

    fingerprint = get_effective_fingerprint(conn, volume_id)  # 两级 fallback，None 时不抛

    constants = {
        "drift_threshold": 0.10,
        "max_edit_rounds": 3,
        "word_count_target": (3000, 5000),
    }

    return {
        "beat_contracts": beat_contracts,
        "reader_disclosed_secrets": _reader_disclosed_secrets(conn),
        "fingerprint": fingerprint,
        "constants": constants,
    }
