# src/bedrock/orchestration/boot_context.py
"""装配子代理启动上下文：beat 契约 + reader-disclosed secrets + StyleTemplate 指纹 + constants。

visibility 边界：只注入 reader_disclosure/public（读者此刻已知）。**有意不注入
character_epistemic 轴**——ChapterWriter 负责叙述，不该拿"某角色私下知道什么"的原始秘密，
那属于未来 POV 接地检查的消费方。POV 感知注入（按本章 POV 角色过滤 character_epistemic）
留待该检查落地时再加。"""
from src.bedrock.repositories.plot_tree import list_beats_in_chapter, list_paragraphs_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.style.template_repo import get_effective_fingerprint
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.orchestration.l2_pipeline import DRIFT_THRESHOLD  # 单一真相源，防与 L2 门禁漂移


def _reader_disclosed_secrets(conn):
    """只取 reader_disclosure 轴 + public vis_mode 的 secret（不泄露 secret_until/faction）。

    public = 读者全局已知；vis_ref 的章级揭示时机尚未建模（默认 '{}'），故按全局 public 注入。"""
    rows = conn.execute(
        "SELECT character_id, key, value FROM character_secret "
        "WHERE vis_axis='reader_disclosure' AND vis_mode='public'").fetchall()
    return [dict(r) for r in rows]


def _prev_chapter_tail(conn, chapter_id, target_chars=400, hard_max=600):
    """上一章(global_number-1)的收尾正文，作章际交接信号。

    按【字符预算 + 段落对齐】：从末段向前累加整段，直到≈target_chars，且不超过 hard_max
    （停在段落边界，绝不切半段）。保底至少含末段（哪怕末段超 hard_max）。
    取舍：给太少（几十字）只有碎片画面接不上场景；给太多（整章）污染本章 writer 上下文、
    引发风格串台/复述。几百字≈"收尾那一刻的场景"，画面/语气/悬念都在，又不灌全文。
    跨卷亦生效（global_number 全局）。无前章/前章无段落 → None。"""
    cur = conn.execute(
        "SELECT global_number FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    if not cur or cur["global_number"] <= 1:
        return None
    prev_id = chapter_id_by_global(conn, cur["global_number"] - 1)
    if prev_id is None:
        return None
    paras = list_paragraphs_in_chapter(conn, prev_id)
    if not paras:
        return None
    tail, total = [], 0
    for p in reversed(paras):
        t = p["text"]
        if tail and total + len(t) > hard_max:   # 已有内容且将超上限 → 停在段落边界
            break
        tail.append(t)
        total += len(t)
        if total >= target_chars:
            break
    return "\n\n".join(reversed(tail))


def get_chapter_boot_context(conn, chapter_id, volume_id):
    """返回 {beat_contracts, reader_disclosed_secrets, fingerprint, constants, prev_chapter_tail}。"""
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)

    fingerprint = get_effective_fingerprint(conn, volume_id)  # 两级 fallback，None 时不抛

    # drift_threshold 与 L2 门禁共享 l2_pipeline.DRIFT_THRESHOLD（防双真相源漂移）。
    # max_edit_rounds/word_count_target 起步值；volume_type_matrix 尚未承载这些键，SP5 可考虑上提。
    constants = {
        "drift_threshold": DRIFT_THRESHOLD,
        "max_edit_rounds": 3,
        "word_count_target": (3000, 5000),
    }

    return {
        "beat_contracts": beat_contracts,
        "reader_disclosed_secrets": _reader_disclosed_secrets(conn),
        "fingerprint": fingerprint,
        "constants": constants,
        "prev_chapter_tail": _prev_chapter_tail(conn, chapter_id),
    }
