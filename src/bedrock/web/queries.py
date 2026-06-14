"""SP6-C Web UI 纯查询：POV 矩阵聚合 + 卷列表。新写聚合 SQL（既有 plot_tree 无 distinct-pov 函数）。"""


def list_volumes_simple(conn):
    """卷列表（id/number/name），按 number 升序。卷选择器数据源。"""
    return [dict(r) for r in conn.execute(
        "SELECT id, number, name FROM volume ORDER BY number").fetchall()]


def pov_matrix(conn, volume_id):
    """POV 矩阵数据：{volume_name, characters:[{id,name}], chapters:[{id,global_number,title,povs:set}]}。
    NULL POV beat 不产角色列（H5）。"""
    vrow = conn.execute("SELECT number, name FROM volume WHERE id=?", (volume_id,)).fetchone()
    volume_name = vrow["name"] if vrow else None

    char_rows = conn.execute(
        "SELECT DISTINCT b.pov_character_id AS cid, c.name "
        "FROM beat b JOIN chapter ch ON b.chapter_id=ch.id "
        "JOIN character c ON b.pov_character_id=c.id "
        "WHERE ch.volume_id=? AND b.pov_character_id IS NOT NULL "
        "ORDER BY b.id", (volume_id,)).fetchall()
    characters = [{"id": r["cid"], "name": r["name"]} for r in char_rows]

    chapters = []
    ch_rows = conn.execute(
        "SELECT id, global_number, title FROM chapter WHERE volume_id=? ORDER BY global_number",
        (volume_id,)).fetchall()
    for ch in ch_rows:
        povs = {r["pov_character_id"] for r in conn.execute(
            "SELECT pov_character_id FROM beat WHERE chapter_id=? AND pov_character_id IS NOT NULL",
            (ch["id"],)).fetchall()}
        chapters.append({"id": ch["id"], "global_number": ch["global_number"],
                         "title": ch["title"], "povs": povs})
    return {"volume_name": volume_name, "characters": characters, "chapters": chapters}
