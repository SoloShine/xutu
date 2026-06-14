"""SP6-A 只读 CLI 工具集：export / diagnose / show_review_report / diff 的纯函数。
diagnose / show_review_report / diff 完全不写 DB；export 仅写 export_manifest（短事务）。
正文 SSOT = paragraph 表，export 单向导出绝不回填。"""
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter


def chapter_filename(global_number):
    """global_number → 'ch{NN}'（≥2 位补零，与既有 output/ 一致）。
    export 写文件、diff 读文件共用，保证命名一致。"""
    return f"ch{global_number:02d}"


def render_chapter_body(conn, chapter_id, fmt):
    """渲染单章正文 + 章标题（不含卷/书标题）。
    md: '### 第N章 标题' + 段落（按 seq，空行分隔）
    txt: '第N章 标题'（正文行）+ 段落
    段落按 seq 排序，只取 text，不读 role。paragraph 主键 para_id（非 id）。"""
    ch = conn.execute(
        "SELECT global_number, title FROM chapter WHERE id=?",
        (chapter_id,)).fetchone()
    if ch is None:
        raise ValueError(f"chapter id={chapter_id} 不存在")
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    body = "\n\n".join(p["text"] for p in paragraphs)
    if fmt == "md":
        return f"### 第{ch['global_number']}章 {ch['title']}\n\n{body}"
    return f"第{ch['global_number']}章 {ch['title']}\n\n{body}"
