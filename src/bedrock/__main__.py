# src/bedrock/__main__.py
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from src.bedrock.init_project import init_project
from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.orchestration.l2_pipeline import run_l2
from src.bedrock.orchestration.boot_context import get_chapter_boot_context
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.orchestration.review_flag import (
    mark_unresolved,
    mark_polish_broke_beat,
    mark_forced_persist_failed,
    mark_advisory_drift,
)
from src.bedrock.orchestration.runtime_collect import write_runtime
from src.bedrock.orchestration.watchdog import run_watchdog
from src.bedrock.orchestration.cross_volume_gate import check_cross_volume_debt
from src.bedrock.orchestration.review_flag import get_review_flag, compute_has_flag, ensure_flag, _upsert
from src.bedrock.repositories.governance import add_amendment
from src.bedrock.repositories.plot_tree import (
    create_paragraph, list_beats_in_chapter, list_paragraphs_in_chapter,
    set_chapter_status, clear_chapter_paragraphs, mark_beats_written,
    update_paragraph_text, insert_paragraph_at, delete_paragraph, reorder_paragraphs,
)
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.checks.proper_nouns import find_proper_noun_variants


def _chapter_id(conn, global_number):
    """global_number → chapter.id（委托共享函数，保 CLI 友好报错）。"""
    return chapter_id_by_global(conn, global_number)


# 段落内可能的 beat 标记：行首 @@beat:N@@ 或 【beat:N】 或 === beat N ===
_BEAT_MARKER = re.compile(r"^\s*(?:@@beat:(\d+)@@|【beat:(\d+)】|={2,}\s*beat\s*(\d+)\s*={2,})\s*$")

# agent 元叙述前置语（"我将直接撰写本章/遵循beat契约…"）—— ChapterWriter 偶尔把开场白当正文吐出，
# L2 语义盲查不出。落盘前剥掉开头连续的此类段，防污染 SSOT。
_META_PREAMBLE = re.compile(
    r"^\s*(我|下面|本[章节]|首先|好的?|没问题)[^。\n]{0,40}?"
    r"(撰写|写一?篇?|创作|生成|遵循|按照|依照|遵循|节拍|beat|契约|既定|语调|风格|要求|prompt)")


def _is_meta_preamble(text):
    """是否为 agent 自述前置语（非小说正文）。短段 + 第一人称/指令词 + 写作任务词。"""
    t = text.strip()
    return len(t) <= 60 and bool(_META_PREAMBLE.match(t))


# 纯分隔符/符号段（"——"、"---"、"***"、孤立星号等），agent 前置语常带，非正文。
_SEP_ONLY = re.compile(r"^[\s—–\-_=*~·•#※　]+$")


def _is_lead_junk(text):
    """开头应剥除的垃圾段：agent 自述前置语 / 纯分隔符段 / 管线术语回显 / 修复过程叙述。"""
    t = text.strip()
    if not t:
        return True
    return (_is_meta_preamble(t) or bool(_SEP_ONLY.match(t))
            or _is_pipeline_echo(t) or _is_repair_narration(t))


# 管线术语（提示词/boot context/pov/节拍N/契约…）——agent 偶尔把 boot context 或 beat 摘要
# 回显成开头段。这些词基本不会出现在小说正文开头，作 lead-junk 剥除。
_PIPELINE_ECHO = re.compile(r"(提示词|boot[ _-]?context|叙事目的|视角角色|\bpov\b|fingerprint|"
                            r"beat\s*契约|节拍\s*\d|系统重查)")


def _is_pipeline_echo(text):
    """开头短段是否像管线术语回显（boot context / beat 摘要等），非小说正文。"""
    t = text.strip()
    return len(t) <= 90 and bool(_PIPELINE_ECHO.search(t))


# agent 修复过程叙述（repair 轮的思考过程被当正文吐在开头）——
# "我需要修复 beat2 的违规：…"/"我将在 beat 2 相关段落加入陆衡的出场,保持其余原文不变"。
# 比 ChapterWriter 前置语更长(~100字)、词汇不同(修复/加入/保持原文),_META_PREAMBLE 漏判。
# 单独识别,放宽长度(≤220);只剥开头连续段,不拒整章。
_REPAIR_NARRATION = re.compile(
    r"^\s*我(需要|要|将|会|来)[^。\n]{0,45}?"
    r"(修复|加入|补上?|删[除去]?|改写?|重写|调整|判断(哪部分|属于)|保持(其余|原文)|出场|归属)"
)


def _is_repair_narration(text):
    """开头段是否像 repair agent 的过程叙述（非小说正文）。"""
    t = text.strip()
    return len(t) <= 220 and bool(_REPAIR_NARRATION.search(t))


# agent 工作日志特征词（修复汇报/操作记录/管线术语）——这类内容绝不该当正文入库。
# 命中 ≥2 个不同特征 → 判为工作日志，commit-paragraphs 拒绝（防 Fix agent 把日志覆盖成正文）。
_WORKLOG_TOKENS = (
    "操作记录", "修复完成", "修复目标", "已删除", "已通过", "已修复", "修改前后",
    "para_id", "surgical", "edit-paragraphs", "commit-paragraphs", "run-l2", "seq=",
    "l2 硬门禁", "l2检测", "l2门禁", "违规", "真相之源", "标准设定",
    "节拍契约依然", "手术式", "元数据残留", "删除该 paragraph", "以下是",
)


def _looks_like_worklog(raw):
    """输入是否像 agent 工作日志而非小说正文（≥2 个特征词命中）。"""
    low = raw.lower()
    return sum(1 for t in _WORKLOG_TOKENS if t in low) >= 2


# 中文正文标点归一化：半角 , . : ; ! ? → 全角（仅 CJK 上下文，代码/数字不动）。
# writer 常吐半角 ":,"（句号碰巧全角），中文阅读体验差。落盘前确定性归一，零 LLM。
_CJK_CHAR = re.compile(r'[一-鿿、-〃〈-〿＀-￯」』）】》”“’]')
_HALF_TO_FULL = {',': '，', ':': '：', ';': '；', '!': '！', '?': '？'}


def _normalize_cjk_punctuation(text):
    """半角标点在 CJK 字之后 → 全角。句号 . 仅 CJK 后且后非数字时转 。"""
    out = []
    for i, ch in enumerate(text):
        prev = text[i - 1] if i > 0 else ''
        if ch in _HALF_TO_FULL and _CJK_CHAR.match(prev):
            out.append(_HALF_TO_FULL[ch])
        elif ch == '.' and _CJK_CHAR.match(prev) and not (i + 1 < len(text) and text[i + 1].isdigit()):
            out.append('。')
        else:
            out.append(ch)
    return ''.join(out)


# 文风气味计数："不是A(而)是B" 句式 + 破折号。参考好作品 notXisY≈0.15%、96%段无破折号，
# 故这俩超量即气味异常（writer 偷懒路径）。落盘后只计数告警，不拒（硬禁靠 prompt）。
# 用 lexicon 统一正则(四变体:无标点/而是/逗号/句号分割),段落级——与 extractor/style_drift 一致。
from src.bedrock.style.lexicon import NOTXISY_PATTERN
_NOTXISY = re.compile(NOTXISY_PATTERN)


def _style_smells(text):
    """返回 (notXisY数, 破折号段标记数)。"""
    notx = len(_NOTXISY.findall(text))
    dash = text.count('——') + text.count('—')  # 破折号(双/单 em-dash)
    return notx, dash


def _split_paragraphs(raw):
    """正文 → [(beat_seq_or_None, text), ...]。
    - 空行分段；丢弃空白段。
    - 行首 beat 标记（如 @@beat:2@@）标记其后段落归属的 beat sequence；
      无标记的段落 beat_seq=None（由 _commit_paragraphs 按章内 beat 兜底分配）。"""
    blocks = re.split(r"\n\s*\n", raw)
    out, current_beat = [], None
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        m = _BEAT_MARKER.match(b)
        if m:
            current_beat = int(next(g for g in m.groups() if g))
            # 标记行本身不含正文；若同行后跟正文则取标记后部分
            rest = _BEAT_MARKER.sub("", b).strip()
            if rest:
                out.append((current_beat, rest))
            continue
        out.append((current_beat, b))
    return out


def _commit_paragraphs(conn, chapter_id, raw, role="narration"):
    """正文纯文本 → 入库 paragraph（幂等：先清空该章段落再重写），章状态→drafted。

    beat 归属策略：
      - 显式标记段：用标记的 beat sequence。
      - 无标记：若全章仅 1 个 beat，全部挂它；若多 beat，按 beat 顺序均分 contiguous 段。
    返回 {chapter_id, paragraph_count, beats_used, status}。"""
    # 安全网：agent 工作日志（"修复完成。操作记录：…"）绝不该当正文入库。
    # 命中即拒绝，不清空 DB——防卷 Fix agent 把日志覆盖成正文（曾毁 ch1/8/11）。
    if _looks_like_worklog(raw):
        sys.exit("commit-paragraphs: 拒绝入库——输入像是 agent 工作日志/操作记录，而非小说正文。"
                 "（Fix agent 应返回整章正文，不是修复汇报）")
    # A1:剥离残留元文本(指标自评/路径/分隔符等,逃脱 workflow extractProse 层的兜底)。
    # 重度污染(清洗后 <MIN_PROSE_CHARS)→ 拒绝,force re-submit,防垃圾入库。
    from src.bedrock.checks.prose_hygiene import sanitize_prose, MIN_PROSE_CHARS
    cleaned, removed, preview = sanitize_prose(raw)
    if removed:
        print(f"commit-paragraphs: 剥离 {removed} 段元文本 {preview}", file=sys.stderr)
    if len(cleaned) < MIN_PROSE_CHARS:
        sys.exit(f"commit-paragraphs: 拒绝入库——清洗后正文仅 {len(cleaned)} 字 "
                 f"(下限 {MIN_PROSE_CHARS})，疑似重度污染，请重交纯正文。")
    paras = _split_paragraphs(cleaned)
    if not paras:
        sys.exit("commit-paragraphs: stdin 无有效段落（空正文？）")

    # 剥离开头的垃圾段（agent 自述前置语 / 纯分隔符"——"等），遇正文即停；至少留 1 段。
    while len(paras) > 1 and _is_lead_junk(paras[0][1]):
        paras.pop(0)

    beats = list_beats_in_chapter(conn, chapter_id)
    if not beats:
        sys.exit(f"commit-paragraphs: 章 {chapter_id} 无 beat 契约，无法落盘")
    seq_to_id = {b["sequence"]: b["id"] for b in beats}
    id_set = {b["id"] for b in beats}   # 标记亦接受 beat_id（beat_contract 只暴露 beat_id）
    beat_ids = [b["id"] for b in beats]

    # 解析每段 beat_id
    beat_ids_for_para = []
    for (bseq, _text) in paras:
        bid = None
        if bseq is not None:
            if bseq in seq_to_id:        # 标记 = sequence
                bid = seq_to_id[bseq]
            elif bseq in id_set:         # 标记 = beat_id
                bid = bseq
        beat_ids_for_para.append(bid)

    # 兜底：未标记段
    if any(b is None for b in beat_ids_for_para):
        if len(beats) == 1:
            only = beat_ids[0]
            beat_ids_for_para = [b if b is not None else only for b in beat_ids_for_para]
        else:
            # 多 beat：把未标记段按顺序 contiguous 均分到各 beat
            n = len(paras)
            for i in range(n):
                if beat_ids_for_para[i] is None:
                    beat_ids_for_para[i] = beat_ids[min(i * len(beats) // n, len(beats) - 1)]

    clear_chapter_paragraphs(conn, chapter_id)
    smell_notx = smell_dash = 0
    for seq_i, ((_bseq, text), bid) in enumerate(zip(paras, beat_ids_for_para), start=1):
        ntext = _normalize_cjk_punctuation(text)   # 半角标点 → 全角（落盘前归一）
        nx, nd = _style_smells(ntext)
        smell_notx += nx
        smell_dash += nd
        chash = hashlib.sha256(ntext.encode("utf-8")).hexdigest()
        create_paragraph(conn, chapter_id, seq_i, ntext, chash, bid, role)
    mark_beats_written(conn, sorted(set(beat_ids_for_para)))
    # schema CHECK: status ∈ {planned, writing, completed}；正文落盘 → writing。
    set_chapter_status(conn, chapter_id, "writing")
    # 文风气味精查（不阻塞）：notXisY / 破折号超参考阈值(0.15%/4%)则告警，prompt 已硬禁。
    if smell_notx or smell_dash:
        n_paras = len(paras) or 1
        print(f"commit-paragraphs: 文风气味 notXisY={smell_notx}({smell_notx*100//n_paras}%段) "
              f"破折号={smell_dash}({smell_dash*100//n_paras}%段)——参考好作品均≈0，prompt 已禁，复查",
              file=sys.stderr)
    return {
        "chapter_id": chapter_id,
        "paragraph_count": len(paras),
        "beats_used": sorted(set(beat_ids_for_para)),
        "status": "writing",
        "style_smells": {"notXisY": smell_notx, "dash": smell_dash},
    }


def _export_chapter_json(conn, project_path, chapter_id, global_number, stage):
    """章节结构化 JSON 备份（冗余用）：段落 + meta + 字数。
    写到 <project>/exports/json/ch<NN>.<stage>.json。stage ∈ draft|first_review|final。
    用于管线各 checkpoint 快照：即使 DB 被覆盖（如卷 Fix 事故）也可从此恢复正文。"""
    ch = conn.execute(
        "SELECT global_number, title, status, volume_id FROM chapter WHERE id=?",
        (chapter_id,)).fetchone()
    paras = conn.execute(
        "SELECT seq, beat_id, role, text FROM paragraph WHERE chapter_id=? ORDER BY seq",
        (chapter_id,)).fetchall()
    full = "".join(p["text"] for p in paras)
    word_count = len(re.findall(r"[一-鿿]", full))
    import datetime
    payload = {
        "project": project_path.name,
        "stage": stage,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "chapter": {
            "global_number": ch["global_number"],
            "title": ch["title"],
            "status": ch["status"],
            "volume_id": ch["volume_id"],
        },
        "word_count": word_count,
        "paragraph_count": len(paras),
        "paragraphs": [
            {"seq": p["seq"], "beat_id": p["beat_id"], "role": p["role"], "text": p["text"]}
            for p in paras],
    }
    out_dir = project_path / "exports" / "json"
    out_dir.mkdir(parents=True, exist_ok=True)
    nn = f"{global_number:02d}"
    out_path = out_dir / f"ch{nn}.{stage}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _import_chapter_json(conn, project_path, chapter_id, global_number, stage):
    """从 JSON 备份忠实恢复章节：清空该章段落，按备份的 seq/beat_id/role 重建。
    备份-恢复闭环的恢复端（卷 Fix 事故、误改等均可从此恢复）。"""
    nn = f"{global_number:02d}"
    src = project_path / "exports" / "json" / f"ch{nn}.{stage}.json"
    if not src.exists():
        sys.exit(f"import-chapter-json: 备份不存在 {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    paras = data.get("paragraphs", [])
    if not paras:
        sys.exit(f"import-chapter-json: 备份 {src} 无段落")
    clear_chapter_paragraphs(conn, chapter_id)
    for p in paras:
        text = p["text"]
        chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        create_paragraph(conn, chapter_id, p["seq"], text, chash, p.get("beat_id"), p.get("role", "narration"))
    mark_beats_written(conn, [b["id"] for b in list_beats_in_chapter(conn, chapter_id)])
    set_chapter_status(conn, chapter_id, "writing")
    return {"chapter_id": chapter_id, "stage": stage, "restored_from": str(src),
            "paragraph_count": len(paras), "word_count": data.get("word_count")}


def _resolve_beat_for_insert(conn, chapter_id, after_seq):
    nbr = conn.execute(
        "SELECT beat_id FROM paragraph WHERE chapter_id=? AND seq<=? "
        "ORDER BY seq DESC LIMIT 1", (chapter_id, after_seq)).fetchone()
    if nbr and nbr["beat_id"] is not None:
        return nbr["beat_id"]
    beats = list_beats_in_chapter(conn, chapter_id)
    return beats[0]["id"] if beats else None


def _check_proper_nouns(conn, chapter_id):
    """专名硬校验(零 LLM,Unit D)。扫该章段落,白名单=character.name+location.name。

    canonical_seen = 全部白名单名(单章 CLI 视所有规范名为已确立;workflow 可后续细化到本章+前序)。
    Tier-1(单候选+已确立+非歧义词)→ 产出 update ops(段落文本内 variant→canonical 全替换),不自行落盘。
    Tier-2(歧义/未确立/歧义常用词)→ escalate 列表。
    写 flag:确保 flag 行存在;若 tier1 自动改则把 autoedit 痕迹存入 advisory_drift(现有自由 JSON 列,
    chapter_review_flag 表无 proper_noun_autoedit 列,不擅改 schema)。amendment 痕迹由 edit-paragraphs 落。
    返回 {"ops":[...],"escalate":[...],"autoedit_count":N}。"""
    whitelist = {"chars": [], "places": []}
    for r in conn.execute("SELECT name FROM character").fetchall():
        whitelist["chars"].append(r["name"])
    for r in conn.execute("SELECT name FROM location").fetchall():
        whitelist["places"].append(r["name"])
    canon_all = whitelist["chars"] + whitelist["places"]
    canonical_seen = set(canon_all)

    paras = list_paragraphs_in_chapter(conn, chapter_id)
    ops, escalate, autoedit = [], [], []
    for p in paras:
        text = p["text"] or ""
        findings = find_proper_noun_variants(text, whitelist, canonical_seen)
        if not findings:
            continue
        new_text = text
        para_touched = False
        for f in findings:
            if f["tier"] == "tier1":
                new_text = new_text.replace(f["variant"], f["canonical"])
                para_touched = True
                autoedit.append({"para_id": p["para_id"], "variant": f["variant"],
                                 "canonical": f["canonical"]})
            else:
                escalate.append({"para_id": p["para_id"], "variant": f["variant"],
                                 "candidates": f["canonical"]})
        if para_touched and new_text != text:
            ops.append({"op": "update", "para_id": p["para_id"], "text": new_text})

    ensure_flag(conn, chapter_id)
    if autoedit:
        _upsert(conn, chapter_id, {
            "advisory_drift": json.dumps(
                {"proper_noun_autoedit": autoedit}, ensure_ascii=False)})
    return {"ops": ops, "escalate": escalate, "autoedit_count": len(autoedit)}


def _apply_paragraph_ops(conn, chapter_id, ops):
    """段落级编辑写面：按序应用 update/insert/delete/reorder（事务化）。
      {"op":"update","para_id":N,"text":"..."}
      {"op":"insert","after_seq":N,"text":"..."}        # after_seq=0 → 章首
      {"op":"delete","para_id":N}
      {"op":"reorder","order":[para_id,...]}            # 必须是该章全部 para_id 的排列
    应用后：章状态→writing，已落段落的 beat→written。返回 {applied, paragraph_count}。"""
    if not isinstance(ops, list) or not ops:
        sys.exit("edit-paragraphs: stdin 需为非空 ops 数组")
    applied = []
    try:
        for op in ops:
            kind = op.get("op")
            if kind == "update":
                update_paragraph_text(conn, int(op["para_id"]), op["text"])
            elif kind == "insert":
                bid = _resolve_beat_for_insert(conn, chapter_id, int(op.get("after_seq", 0)))
                text = op["text"]
                chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                insert_paragraph_at(conn, chapter_id, int(op.get("after_seq", 0)),
                                    text, chash, bid, "narration")
            elif kind == "delete":
                delete_paragraph(conn, int(op["para_id"]))
            elif kind == "reorder":
                reorder_paragraphs(conn, chapter_id, [int(x) for x in op["order"]])
            else:
                sys.exit(f"edit-paragraphs: 未知 op {kind!r}")
            applied.append(kind)
        beat_ids = [b["id"] for b in list_beats_in_chapter(conn, chapter_id)]
        mark_beats_written(conn, beat_ids)
        set_chapter_status(conn, chapter_id, "writing")
    except Exception as e:
        conn.rollback()
        sys.exit(f"edit-paragraphs 回滚: {e}")
    count = conn.execute(
        "SELECT COUNT(*) FROM paragraph WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
    return {"chapter_id": chapter_id, "applied": applied, "paragraph_count": count}


def _write_review_report(report_path, volume, payload):
    """拼装 review_report_vol{N}.md 并落盘（强制，治 Vol15 报告丢失）。

    payload 结构：{findings: {actionable:[...]|{...}}, outcomes: {chN: state},
                   watchdog: {...}, debt: {...}}。
    容错：各段缺失时输出空段而非崩溃（CLI 薄封装，不挡 e2e）。"""
    findings = payload.get("findings") or {}
    outcomes = payload.get("outcomes") or {}
    watchdog = payload.get("watchdog") or {}
    debt = payload.get("debt") or {}

    # findings.actionable 可能是 list 或 dict；统一拍平为 (chapter, f) 行
    actionable = findings.get("actionable") if isinstance(findings, dict) else None
    lines = [f"# VolumeReview 报告 — 卷 {volume}", ""]

    lines.append("## 旗章发现（actionable）")
    if isinstance(actionable, list) and actionable:
        for f in actionable:
            if isinstance(f, dict):
                chs = f.get("chapters")
                ch = ",".join(str(c) for c in chs) if isinstance(chs, list) and chs else f.get("chapter", "?")
                fi = f.get("fix_instruction", "")
                ia = f.get("is_actionable", "")
            else:
                ch, fi, ia = "?", str(f), ""
            lines.append(f"- ch{ch} [is_actionable={ia}]: {fi}")
    elif isinstance(actionable, dict) and actionable:
        for ch, f in actionable.items():
            fi = f.get("fix_instruction", "") if isinstance(f, dict) else str(f)
            ia = f.get("is_actionable", "") if isinstance(f, dict) else ""
            lines.append(f"- ch{ch} [is_actionable={ia}]: {fi}")
    else:
        lines.append("- （无 actionable 发现）")
    lines.append("")

    lines.append("## 修正结果（三状态）")
    if outcomes:
        for ch, state in outcomes.items():
            lines.append(f"- ch{ch}: {state}")
    else:
        lines.append("- （无编辑章）")
    lines.append("")

    lines.append("## Watchdog（贴边走 / drift 聚合）")
    if isinstance(watchdog, dict) and watchdog:
        lines.append("```json")
        lines.append(json.dumps(watchdog, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- （无 watchdog 信号）")
    lines.append("")

    lines.append("## 跨卷悬链欠债")
    if isinstance(debt, dict) and debt:
        lines.append("```json")
        lines.append(json.dumps(debt, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- （无欠债）")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(prog="bedrock", description="磐石 V3 小说管线 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="初始化新作品项目")
    p_init.add_argument("path", type=Path)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--force", action="store_true")

    p_runl2 = sub.add_parser("run-l2", help="单章 L2 全量重算（零 LLM）")
    p_runl2.add_argument("--project", type=Path, required=True)
    p_runl2.add_argument("--chapter", type=int, required=True)

    p_style = sub.add_parser("style-check", help="单章文风漂移测量（标量指标 vs 目标,方向性诊断）")
    p_style.add_argument("--project", type=Path, required=True)
    p_style.add_argument("--chapter", type=int, required=True)
    p_style.add_argument("--volume", type=int, required=True)

    p_evstyle = sub.add_parser("extract-volume-style", help="从本卷已写章节 extract 卷级指纹")
    p_evstyle.add_argument("--project", type=Path, required=True)
    p_evstyle.add_argument("--volume", type=int, required=True)

    p_srstyle = sub.add_parser("show-reference-sample", help="读持久化的参考样本+来源(供 /analyze-style)")
    p_srstyle.add_argument("--project", type=Path, required=True)
    p_srstyle.add_argument("--volume", type=int, default=None)

    p_rsa = sub.add_parser("refresh-style-actual", help="重算实测指纹并写缓存(章写完调)")
    p_rsa.add_argument("--project", type=Path, required=True)
    p_rsa.add_argument("--volume", type=int, default=None)

    p_sdir = sub.add_parser("set-style-directive", help="写文风指令+来源(/analyze-style 落库)")
    p_sdir.add_argument("--project", type=Path, required=True)
    p_sdir.add_argument("--directive", required=True)
    p_sdir.add_argument("--source", default="")
    p_sdir.add_argument("--scope", choices=["work", "volume"], default="work")
    p_sdir.add_argument("--volume", type=int, default=None)

    p_boot = sub.add_parser("boot-context", help="装配子代理启动上下文")
    p_boot.add_argument("--project", type=Path, required=True)
    p_boot.add_argument("--chapter", type=int, required=True)
    p_boot.add_argument("--volume", type=int, required=True)

    p_verify = sub.add_parser("verify-persisted", help="强制落盘门禁")
    p_verify.add_argument("--project", type=Path, required=True)
    p_verify.add_argument("--chapter", type=int, required=True)
    p_verify.add_argument("--export-path", type=Path, default=None)

    p_commit = sub.add_parser(
        "commit-paragraphs",
        help="正文入库（stdin=本章正文纯文本；幂等重写，状态→drafted）")
    p_commit.add_argument("--project", type=Path, required=True)
    p_commit.add_argument("--chapter", type=int, required=True)
    p_commit.add_argument("--role", default="narration",
                          help="段落 role 默认 narration")

    p_showp = sub.add_parser("show-paragraphs", help="读章节段落 JSON（para_id/seq/beat_id/text）")
    p_showp.add_argument("--project", type=Path, required=True)
    p_showp.add_argument("--chapter", type=int, required=True)

    p_editp = sub.add_parser(
        "edit-paragraphs",
        help="段落级编辑（stdin=ops JSON：update/insert/delete/reorder，事务化）")
    p_editp.add_argument("--project", type=Path, required=True)
    p_editp.add_argument("--chapter", type=int, required=True)

    p_pn = sub.add_parser(
        "check-proper-nouns",
        help="专名硬校验(零 LLM):Tier1 自动 update ops / Tier2 escalate。不自行落盘,ops 交 edit-paragraphs")
    p_pn.add_argument("--project", type=Path, required=True)
    p_pn.add_argument("--chapter", type=int, required=True)

    p_expjson = sub.add_parser(
        "export-chapter-json",
        help="章节结构化 JSON 备份（初稿/一审/二审核稿，冗余备份用）")
    p_expjson.add_argument("--project", type=Path, required=True)
    p_expjson.add_argument("--chapter", type=int, required=True)
    p_expjson.add_argument("--stage", required=True,
                           choices=["draft", "first_review", "final"],
                           help="draft=写完初稿 / first_review=编辑改后一审 / final=卷审后二审核稿(终稿)")

    p_impjson = sub.add_parser(
        "import-chapter-json",
        help="从 JSON 备份恢复章节（清空该章段落，按备份忠实重建 seq/beat_id/role）")
    p_impjson.add_argument("--project", type=Path, required=True)
    p_impjson.add_argument("--chapter", type=int, required=True)
    p_impjson.add_argument("--stage", required=True, choices=["draft", "first_review", "final"])

    p_mark = sub.add_parser("mark-unresolved", help="3轮重试耗尽：写 l2_unresolved=1")
    p_mark.add_argument("--project", type=Path, required=True)
    p_mark.add_argument("--chapter", type=int, required=True)
    p_mark.add_argument("--rule-or-model", type=int, required=True,
                        help="1=疑似规则/模型问题，0=否")

    p_mark_pbb = sub.add_parser("mark-polish-broke-beat")
    p_mark_pbb.add_argument("--project", type=Path, required=True)
    p_mark_pbb.add_argument("--chapter", type=int, required=True)

    p_mc = sub.add_parser("mark-completed",
                          help="人工/卷审后置章为 completed(导出门禁前置状态)")
    p_mc.add_argument("--project", type=Path, required=True)
    p_mc.add_argument("--chapter", type=int, required=True)

    p_mark_fpf = sub.add_parser("mark-forced-persist-failed")
    p_mark_fpf.add_argument("--project", type=Path, required=True)
    p_mark_fpf.add_argument("--chapter", type=int, required=True)

    p_mark_drift = sub.add_parser("mark-advisory-drift")
    p_mark_drift.add_argument("--project", type=Path, required=True)
    p_mark_drift.add_argument("--chapter", type=int, required=True)

    p_collect = sub.add_parser("collect-runtime")
    p_collect.add_argument("--project", type=Path, required=True)
    p_collect.add_argument("--chapter", type=int, required=True)
    p_collect.add_argument("--editing-rounds", type=int, default=0)

    # SP5 治理层：卷级 watchdog / 跨卷门禁 / 旗查询 / 报告落盘 / 人工释放
    p_watchdog = sub.add_parser("run-watchdog", help="跨章 statistical watchdog（贴边走+drift）")
    p_watchdog.add_argument("--project", type=Path, required=True)
    p_watchdog.add_argument("--volume", type=int, required=True, help="volume.id")

    p_debt = sub.add_parser("cross-volume-debt", help="跨卷悬链收敛门禁")
    p_debt.add_argument("--project", type=Path, required=True)
    p_debt.add_argument("--volume", type=int, required=True, help="volume.id")

    p_flag = sub.add_parser("get-review-flag", help="读 SP4 chapter_review_flag + 派生 has_flag")
    p_flag.add_argument("--project", type=Path, required=True)
    p_flag.add_argument("--chapter", type=int, required=True)

    p_report = sub.add_parser("write-review-report", help="拼装 review_report_vol{N}.md 强制落盘")
    p_report.add_argument("--project", type=Path, required=True)
    p_report.add_argument("--volume", type=int, required=True, help="volume.id")

    p_unlock = sub.add_parser("unlock-volume", help="人工释放卷间 BLOCKING（写 amendment 留痕）")
    p_unlock.add_argument("--project", type=Path, required=True)
    p_unlock.add_argument("--volume", type=int, required=True, help="volume.id")
    p_unlock.add_argument("--reason", required=True)

    # SP6-A 只读工具集
    p_export = sub.add_parser("export", help="导出正文（paragraph→文件，单向）")
    p_export.add_argument("--project", type=Path, required=True)
    scope_x = p_export.add_mutually_exclusive_group(required=True)
    scope_x.add_argument("--chapter", type=int, help="global_number")
    scope_x.add_argument("--volume", type=int, help="volume.id")
    scope_x.add_argument("--book", action="store_true")
    p_export.add_argument("--format", choices=["md", "txt"], default="md")
    p_export.add_argument("--final", action="store_true")
    p_export.add_argument("--out", type=Path, default=None)

    p_diag = sub.add_parser("diagnose", help="体检报告（聚合留痕旗/状态/欠债，可选live L2）")
    p_diag.add_argument("--project", type=Path, required=True)
    diag_scope = p_diag.add_mutually_exclusive_group(required=True)
    diag_scope.add_argument("--volume", type=int, help="volume.id")
    diag_scope.add_argument("--book", action="store_true")
    p_diag.add_argument("--with-l2", action="store_true",
                        help="现场跑 run_l2（仅 --volume，禁 --book）")
    p_diag.add_argument("--out", type=Path, default=None)

    p_show = sub.add_parser("show-review-report", help="读 review_report_vol{N}.md")
    p_show.add_argument("--project", type=Path, required=True)
    p_show.add_argument("--volume", type=int, required=True, help="volume.id（文件名以此定位）")
    p_show.add_argument("--escalate-only", action="store_true")
    p_show.add_argument("--plain", action="store_true")
    p_show.add_argument("--out", type=Path, default=None)

    p_diff = sub.add_parser("diff", help="DB↔文件漂移检测（RC3 反向校验）")
    p_diff.add_argument("--project", type=Path, required=True)
    diff_scope = p_diff.add_mutually_exclusive_group(required=True)
    diff_scope.add_argument("--chapter", type=int, help="global_number")
    diff_scope.add_argument("--volume", type=int, help="volume.id")
    diff_scope.add_argument("--book", action="store_true")
    p_diff.add_argument("--format", choices=["md", "txt"], default="md")
    p_diff.add_argument("--final", action="store_true", help="比对 exports/final/ 区")
    p_diff.add_argument("--out", type=Path, default=None)

    args = parser.parse_args()
    if args.cmd == "init":
        init_project(args.path, work_name=args.name, force=args.force)
        print(f"已初始化作品 '{args.name}' 于 {args.path}")
        return

    # 以下子命令都需要 DB 连接
    conn = get_connection(args.project)
    try:
        if args.cmd == "run-l2":
            cid = _chapter_id(conn, args.chapter)
            report = run_l2(conn, cid)
            # 输出 JSON（机器可读，Workflow JS 解析 passed_hard_gate / beat_violations[]）
            # asdict 递归转 BeatViolation dataclass；cross_volume 已在 l2_pipeline 转 dict。
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
        elif args.cmd == "style-check":
            from src.bedrock.checks.style_drift import measure_style_drift
            cid = _chapter_id(conn, args.chapter)
            print(json.dumps(measure_style_drift(conn, cid, args.volume), ensure_ascii=False))
        elif args.cmd == "extract-volume-style":
            from src.bedrock.style.template_repo import save_fingerprint
            rows = conn.execute(
                "SELECT c.id FROM chapter c WHERE c.volume_id=? AND c.status='writing' "
                "ORDER BY c.global_number", (args.volume,)).fetchall()
            if not rows:
                sys.exit(f"extract-volume-style: 卷 {args.volume} 无已写章节(status=writing)")
            cids = [r["id"] for r in rows]
            save_fingerprint(conn, scope="volume", chapter_ids=cids, volume_id=args.volume)
            print(f"卷 {args.volume} 指纹已提取自 {len(cids)} 章(status=writing)")
        elif args.cmd == "show-reference-sample":
            from src.bedrock.style.template_repo import get_style_config
            cfg = get_style_config(conn, args.volume) if args.volume else \
                  __import__("src.bedrock.style.template_repo", fromlist=["get_style_config"]).get_style_config(conn, None)
            import json as _json
            out = {"source": cfg.get("source_work"), "directive": cfg.get("directive"),
                   "directive_source": cfg.get("directive_source"),
                   "directive_stale": cfg.get("directive_stale")}
            row = conn.execute("SELECT reference_sample FROM style_template WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()
            out["sample"] = row["reference_sample"] if row else ""
            print(_json.dumps(out, ensure_ascii=False))
        elif args.cmd == "set-style-directive":
            from src.bedrock.style.template_repo import set_style_config
            rid = set_style_config(conn, args.scope, volume_id=args.volume,
                                   directive=args.directive, directive_source=args.source)
            print(f"directive 已写入 row={rid} scope={args.scope} source={args.source or '(无)'}")
        elif args.cmd == "refresh-style-actual":
            from src.bedrock.checks.style_drift import refresh_actual_cache
            r = refresh_actual_cache(conn, args.volume)
            print(f"实测缓存已刷新: {r.get('chapter_count',0)}章/{r.get('paragraph_count',0)}段 cached={r.get('cached')}")
        elif args.cmd == "boot-context":
            cid = _chapter_id(conn, args.chapter)
            ctx = get_chapter_boot_context(conn, cid, volume_id=args.volume)
            print(json.dumps(ctx, ensure_ascii=False, indent=2))
        elif args.cmd == "verify-persisted":
            cid = _chapter_id(conn, args.chapter)
            ok = verify_chapter_persisted(conn, cid, export_path=args.export_path)
            # A3:无条件保证 flag 行存在(无论 pass/fail),治"过 L2 修复轮的章无 flag 行"漏判。
            from src.bedrock.orchestration.review_flag import ensure_flag
            ensure_flag(conn, cid)
            # Unit B:verify 通过 → completed(可导出)。verify_chapter_persisted 返回 bool。
            if ok:
                set_chapter_status(conn, cid, "completed")
            print("True" if ok else "False")
        elif args.cmd == "commit-paragraphs":
            cid = _chapter_id(conn, args.chapter)
            raw = sys.stdin.buffer.read().decode("utf-8")
            payload = _commit_paragraphs(
                conn, cid, raw, role=args.role)
            print(json.dumps(payload, ensure_ascii=False))
        elif args.cmd == "show-paragraphs":
            cid = _chapter_id(conn, args.chapter)
            rows = conn.execute(
                "SELECT para_id, seq, beat_id, role, text FROM paragraph "
                "WHERE chapter_id=? ORDER BY seq", (cid,)).fetchall()
            out = [{"para_id": r["para_id"], "seq": r["seq"],
                    "beat_id": r["beat_id"], "role": r["role"], "text": r["text"]}
                   for r in rows]
            print(json.dumps(out, ensure_ascii=False))
        elif args.cmd == "check-proper-nouns":
            cid = _chapter_id(conn, args.chapter)
            payload = _check_proper_nouns(conn, cid)
            print(json.dumps(payload, ensure_ascii=False))
        elif args.cmd == "edit-paragraphs":
            cid = _chapter_id(conn, args.chapter)
            try:
                ops = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid ops JSON on stdin: {e}")
            payload = _apply_paragraph_ops(conn, cid, ops)
            print(json.dumps(payload, ensure_ascii=False))
        elif args.cmd == "mark-completed":
            cid = _chapter_id(conn, args.chapter)
            set_chapter_status(conn, cid, "completed")
            print(f"ch{args.chapter} → completed")
        elif args.cmd == "export-chapter-json":
            cid = _chapter_id(conn, args.chapter)
            out = _export_chapter_json(conn, args.project, cid, args.chapter, args.stage)
            print(json.dumps({"path": str(out), "stage": args.stage}, ensure_ascii=False))
        elif args.cmd == "import-chapter-json":
            cid = _chapter_id(conn, args.chapter)
            payload = _import_chapter_json(conn, args.project, cid, args.chapter, args.stage)
            print(json.dumps(payload, ensure_ascii=False))
        elif args.cmd == "mark-unresolved":
            cid = _chapter_id(conn, args.chapter)
            # 显式按 UTF-8 解 stdin（Windows OEM 码页如 cp936 会把 UTF-8 JSON 解成乱码，
            # 后续 ensure_ascii=False 写回时 UnicodeEncodeError）。读 buffer 原始字节再 decode。
            try:
                raw = json.loads(sys.stdin.buffer.read().decode("utf-8"))
                violations = [BeatViolation(**d) for d in raw]
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                sys.exit(f"invalid violations JSON on stdin: {e}")
            mark_unresolved(
                conn, cid, violations,
                likely_rule_or_model_issue=bool(args.rule_or_model))
            print("ok")
        elif args.cmd == "mark-polish-broke-beat":
            cid = _chapter_id(conn, args.chapter)
            mark_polish_broke_beat(conn, cid)
            print("ok")
        elif args.cmd == "mark-forced-persist-failed":
            cid = _chapter_id(conn, args.chapter)
            mark_forced_persist_failed(conn, cid)
            print("ok")
        elif args.cmd == "mark-advisory-drift":
            cid = _chapter_id(conn, args.chapter)
            try:
                drift = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid drift JSON on stdin: {e}")
            mark_advisory_drift(conn, cid, drift)
            print("ok")
        elif args.cmd == "collect-runtime":
            cid = _chapter_id(conn, args.chapter)
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
                invocations = payload.get("invocations", [])
                llm_calls = payload.get("llm_calls", [])
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid runtime JSON on stdin: {e}")
            write_runtime(conn, cid, invocations, llm_calls,
                          editing_rounds=args.editing_rounds)
            print("ok")
        elif args.cmd == "run-watchdog":
            # volume 参数语义 = volume.id（run_watchdog/check_cross_volume_debt 都接 id）
            report = run_watchdog(conn, args.volume)
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
        elif args.cmd == "cross-volume-debt":
            report = check_cross_volume_debt(conn, args.volume)
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
        elif args.cmd == "get-review-flag":
            cid = _chapter_id(conn, args.chapter)
            flag = get_review_flag(conn, cid)
            has_flag = compute_has_flag(flag)
            print(json.dumps({"has_flag": has_flag, "flag": flag},
                             ensure_ascii=False, default=str))
        elif args.cmd == "write-review-report":
            # 读 stdin JSON（findings/outcomes/watchdog/debt）→ 拼装 markdown → 强制落盘（治 Vol15）
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid report JSON on stdin: {e}")
            report_path = args.project / f"review_report_vol{args.volume}.md"
            _write_review_report(report_path, args.volume, payload)
            print(str(report_path))
        elif args.cmd == "unlock-volume":
            # 人工释放卷间 BLOCKING：UPDATE blocking=0 + amendment 留痕（author='human'）
            row = conn.execute(
                "SELECT blocking FROM volume_review WHERE volume_id=?",
                (args.volume,)).fetchone()
            old_blocking = row["blocking"] if row is not None else None
            conn.execute(
                "UPDATE volume_review SET blocking=0 WHERE volume_id=?",
                (args.volume,))
            add_amendment(conn, entity_type="volume_review", entity_id=args.volume,
                          field="blocking", old=str(old_blocking) if old_blocking is not None else None,
                          new="0", reason=args.reason, author="human")
            conn.commit()
            print("ok")
        elif args.cmd == "export":
            from src.bedrock.cli.reader_commands import do_export
            if args.book:
                scope, target = "book", None
            elif args.chapter is not None:
                cid = _chapter_id(conn, args.chapter)   # global_number → id
                scope, target = "chapter", cid
            else:
                scope, target = "volume", args.volume
            result = do_export(conn, args.project, scope, target,
                               args.format, args.final, args.out)
            print(result.path)
        elif args.cmd == "diagnose":
            from src.bedrock.cli.reader_commands import diagnose
            scope = ("book", None) if args.book else ("volume", args.volume)
            report = diagnose(conn, args.project, scope, with_l2=args.with_l2)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(report, encoding="utf-8")
                print(args.out)
            else:
                print(report)
        elif args.cmd == "show-review-report":
            from src.bedrock.cli.reader_commands import show_review_report
            out = show_review_report(args.project, args.volume,
                                     args.escalate_only, args.plain)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(out, encoding="utf-8")
                print(args.out)
            else:
                print(out)
        elif args.cmd == "diff":
            from src.bedrock.cli.reader_commands import detect_drift, render_drift_report
            if args.book:
                scope, target, desc = "book", None, "全书"
            elif args.chapter is not None:
                cid = _chapter_id(conn, args.chapter)
                scope, target, desc = "chapter", cid, f"ch{args.chapter}"
            else:
                scope, target, desc = "volume", args.volume, f"vol(id={args.volume})"
            report = detect_drift(conn, args.project, scope, target, args.format, args.final)
            rendered = render_drift_report(report, desc, args.format, args.final)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(rendered, encoding="utf-8")
                print(args.out)
            else:
                print(rendered)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
