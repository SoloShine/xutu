# src/bedrock/orchestration/boot_context.py
"""装配子代理启动上下文：beat 契约 + reader-disclosed secrets + 角色正典 + StyleTemplate 指纹 + constants。

visibility 边界：只注入 reader_disclosure/public（读者此刻已知）。**有意不注入
character_epistemic 轴**——ChapterWriter 负责叙述，不该拿"某角色私下知道什么"的原始秘密，
那属于未来 POV 接地检查的消费方。POV 感知注入（按本章 POV 角色过滤 character_epistemic）
留待该检查落地时再加。"""
import json
from src.bedrock.repositories.plot_tree import list_beats_in_chapter, list_paragraphs_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.repositories.character import visible_secrets_for_context
from src.bedrock.style.template_repo import get_style_config
from src.bedrock.style.template_repo import get_effective_fingerprint  # 兼容旧引用
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.orchestration.l2_pipeline import DRIFT_THRESHOLD  # 单一真相源，防与 L2 门禁漂移


def _reader_disclosed_secrets(conn, chapter_id):
    """读者【本章此刻】已知的角色秘密：public 恒知 + secret_until 到揭示章解封。

    复用 visible_secrets_for_context（可见性单一真相源），按本章 global_number 解封。
    修临场发挥：原版只取 vis_mode='public'，secret_until 永不解封——揭示章 writer 仍不知
    真身，凭空幻觉（nanhai_gold 周予明 ch11 凭空编了"八岁口子"身世，与 ch6 退休顾问矛盾）。
    现揭示章 writer 拿得到解封的真身，之前的章只给公开面 → 揭示成设计好的演变，非事后异常。"""
    cur = conn.execute("SELECT global_number FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    chapter = cur["global_number"] if cur else 1
    rows = conn.execute(
        "SELECT id, name FROM character ORDER BY (role='protagonist') DESC, id").fetchall()
    out = []
    for r in rows:
        for s in visible_secrets_for_context(conn, r["id"], chapter, None, 'reader_disclosure'):
            out.append({"character_id": r["id"], "character": r["name"],
                        "key": s["key"], "value": s["value"]})
    return out


def _character_canon(conn):
    """角色正典（name/aliases/pronoun/gender/role/personality）——ChapterWriter 据此写一致代词/性别/称呼。
    修 drift：原 boot-context 不注入角色表，writer 无参照，秦禾性别当场飘。现接上库里的正典。"""
    rows = conn.execute(
        "SELECT name, aliases, pronoun, gender, role, personality FROM character "
        "ORDER BY (role='protagonist') DESC, id").fetchall()
    out = []
    for r in rows:
        try:
            aliases = json.loads(r["aliases"]) if r["aliases"] else []
        except (ValueError, TypeError):
            aliases = []
        out.append({"name": r["name"], "aliases": aliases,
                    "pronoun": r["pronoun"], "gender": r["gender"],
                    "role": r["role"], "personality": r["personality"]})
    return out


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
    """返回 {beat_contracts, reader_disclosed_secrets, characters, fingerprint, style_directive,
    style_examples, constants, prev_chapter_tail}。文风(指纹+指令+范例+旋钮)从 style_template 读,可配。"""
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)

    # 文风配置(DB 可配,卷级覆盖作品级→代码默认)。指纹/指令/字数/编辑轮全从这出。
    style = get_style_config(conn, volume_id)
    fingerprint = style["fingerprint"] or get_effective_fingerprint(conn, volume_id)
    # 风格范例(正反例):作者策划的具体段落,注入 writer【风格示范】。{good:[], bad:[]},限 5 条控 token
    ex = style.get("style_examples") or {}
    style_examples = {"good": list(ex.get("good") or [])[:5], "bad": list(ex.get("bad") or [])[:5]}

    constants = {
        "drift_threshold": DRIFT_THRESHOLD,  # 与 L2 门禁共享,不可配(防双真相源)
        "max_edit_rounds": style["max_edit_rounds"],       # DB 可配
        "word_count_target": tuple(style["word_count_target"]),  # DB 可配
        "hygiene": style["hygiene"],                       # DB 可配(notXisY_max/dash_max_per_k)
    }

    return {
        "beat_contracts": beat_contracts,
        "reader_disclosed_secrets": _reader_disclosed_secrets(conn, chapter_id),
        "characters": _character_canon(conn),
        "fingerprint": fingerprint,
        "style_directive": style["directive"],   # 定性文风指令(自由文本,注入 writer)
        "style_examples": style_examples,        # 正反例段落,注入 writer【风格示范】(对照不复述)
        "constants": constants,
        "prev_chapter_tail": _prev_chapter_tail(conn, chapter_id),
    }
