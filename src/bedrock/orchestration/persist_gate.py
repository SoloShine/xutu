# src/bedrock/orchestration/persist_gate.py
import os
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter


def verify_chapter_persisted(conn, chapter_id, export_path=None):
    """强制落盘门禁：paragraphs 入 DB（主，SSOT）+ 可选导出文件存在性。
    paragraphs 行数 == 0 → False（治 Vol15 未落盘）。
    export_path 传入且文件不存在 → False；不传则跳过文件检查。"""
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    if len(paragraphs) == 0:
        return False
    if export_path is not None and not os.path.exists(export_path):
        return False
    return True
