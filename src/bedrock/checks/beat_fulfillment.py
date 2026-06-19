# src/bedrock/checks/beat_fulfillment.py
import json
from dataclasses import dataclass
from src.bedrock.repositories.plot_tree import list_beats_in_chapter, list_paragraphs_in_chapter
from src.bedrock.repositories.character import get_character
from src.bedrock.repositories.beat_link import characters_in_beat
from src.bedrock.repositories.suspense import threads_advanced_at_beat
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.checks.prose_hygiene import is_meta_paragraph


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

        # 规则1: 角色出场
        beat_paras = paras_by_beat.get(beat["id"], [])

        # 规则0b: 非 planned beat 须有 ≥1 段落（防外科删除掏空 / 整章重写时 beat 错位归属）
        if len(beat_paras) == 0:
            violations.append(BeatViolation(
                beat_id=beat["id"], kind="empty_beat",
                detail=f"beat {beat['id']} 状态={beat['status']} 但无任何段落（被删空或整章重写时错位）",
                fix_hint=f"为 beat {beat['id']} 写回至少一段，或在多 beat 章用 @@beat:N@@ 标记重新归属"))
            continue

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

        # 规则2: 悬链迁移
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

    # 规则 non_prose:任何已入库段命中元文本 → 违规(A2 第三层兜底)
    for p in paragraphs:
        if is_meta_paragraph(p["text"]):
            violations.append(BeatViolation(
                beat_id=p["beat_id"] if p["beat_id"] is not None else (beats[0]["id"] if beats else 0),
                kind="non_prose",
                detail=f"段落 seq={p['seq']} 疑似 agent 元文本/工作日志：{p['text'][:30]}",
                fix_hint="删除该 meta 段，仅保留正文"))

    return violations
