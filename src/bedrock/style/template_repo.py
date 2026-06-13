# src/bedrock/style/template_repo.py
import json
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.telemetry import save_style_template
from src.bedrock.style.extractor import extract_fingerprint


def _gather_paragraphs(conn, chapter_ids):
    """收集这些章节的所有 paragraph.text。"""
    paragraphs = []
    for cid in chapter_ids:
        for p in list_paragraphs_in_chapter(conn, cid):
            paragraphs.append(p["text"])
    return paragraphs


def save_fingerprint(conn, scope, chapter_ids, volume_id=None):
    """提取并写回 style_template。fingerprint JSON 内嵌 _scope/_volume_id。"""
    paragraphs = _gather_paragraphs(conn, chapter_ids)
    fingerprint = extract_fingerprint(paragraphs)
    fingerprint["_scope"] = scope
    if scope == "volume" and volume_id is not None:
        fingerprint["_volume_id"] = volume_id
    save_style_template(
        conn,
        fingerprint=fingerprint,
        source_works=[scope],
        sample_chapters=chapter_ids,
    )


def get_effective_fingerprint(conn, volume_id):
    """两级 fallback：卷级 → 作品级 → None。"""
    # 1. 卷级
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "volume" and fp.get("_volume_id") == volume_id:
            return fp
    # 2. 作品级
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "work":
            return fp
    # 3. 都无
    return None


def list_fingerprints(conn, scope=None):
    """列指纹（可选按 scope 过滤）。返回 fingerprint dict 列表。"""
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    out = []
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if scope is None or fp.get("_scope") == scope:
            out.append(fp)
    return out
