# src/bedrock/db/chapter_lookup.py
"""共享 helper：global_number → chapter.id。CLI 与 MCP server 共用，避免 mcp_server 逆向依赖 __main__。"""


def chapter_id_by_global(conn, global_number):
    """global_number → chapter.id。找不到 raise SystemExit（CLI 直接退出 / MCP 层 try-except catch）。"""
    row = conn.execute(
        "SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if row is None:
        raise SystemExit(f"找不到 global_number={global_number} 的章节")
    return row["id"]
