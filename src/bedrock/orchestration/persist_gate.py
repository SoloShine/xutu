# src/bedrock/orchestration/persist_gate.py
import os
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.orchestration.l2_pipeline import run_l2


def verify_chapter_persisted(conn, chapter_id, export_path=None):
    """强制落盘门禁:paragraphs 入 DB(主,SSOT)+ L2 硬门禁通过 + 可选导出文件存在。
    completed 蕴含 L2-clean:破损章(L2 不过)→ False → 不置 completed。"""
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    if len(paragraphs) == 0:
        return False
    if not run_l2(conn, chapter_id).passed_hard_gate:
        return False
    if export_path is not None and not os.path.exists(export_path):
        return False
    return True
