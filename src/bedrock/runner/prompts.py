# src/bedrock/runner/prompts.py
"""Writer prompt。从 .js writerPrompt 忠实移植【创意内容】(beat/正典/指纹/指令/范例/secrets/
prev_tail/hygiene/multi-beat),去掉 .js 的 tool-loop 协议——runner 里 writer 是单次 LLM 出整章正文,
commit/L2/迭代全由 Python 图管,LLM 只管写。重写时附 L2 违规定向反馈。"""
import json

HYGIENE_RULES = """【文风硬约束·必须遵守】(统计自对标参考作品)
- 标点全角:中文正文一律 。,:;!? 已由系统归一,但你也要自觉,不要吐半角 , . : ; ! ?
- 禁"不是A是B"句式及一切变体("不是x。是x,"/"并非…而是"/"不在于…在于"等)——一句都不许出现,这是偷懒句式,参考好作品仅 0.15%。
- 慎用破折号(——):参考作品 96% 段落不用,非必要坚决不写;要转折用句号断句。
- 段落短促、视角克制、不堆砌感官形容词;少用"地"字副词尾。"""


def writer_prompt(ctx: dict, chapter_global: int, volume_id: int,
                  word_target: tuple, violations_feedback: str = "") -> str:
    """构造 writer 单次生成 prompt。

    ctx: boot context。violations_feedback: 重写时附的 L2 违规(空=首版)。
    返回 prompt 字符串;LLM 应只输出整章正文(段间空行,多 beat 用 @@beat:<id>@@ 标记,无标题/围栏/旁白)。
    """
    beats = ctx.get("beat_contracts") or []
    multi = beats if len(beats) > 1 else []

    prev = (["【上一章收尾】(本章开篇须自然承接其画面/语气/悬念,禁止复述原文):",
             ctx["prev_chapter_tail"], ""]
            if ctx.get("prev_chapter_tail") else ["(本章为开篇,无前章。)", ""])

    chars = ctx.get("characters") or []
    canon = ([f"【角色正典·必须严格遵守】代词/性别/称呼/性格按下表,不得擅改"
              f"(如 {chars[0]['name']}={chars[0].get('pronoun')}):",
              json.dumps([{"name": c.get("name"), "pronoun": c.get("pronoun"),
                           "gender": c.get("gender"), "role": c.get("role"),
                           "personality": c.get("personality")} for c in chars],
                         ensure_ascii=False, indent=2), ""]
             if chars else [])

    directive = (["【文风指令·定性要求(高于统计指纹,必须贯彻)】", ctx["style_directive"], ""]
                 if ctx.get("style_directive") else [])

    ex = ctx.get("style_examples") or {}
    demo = (["【风格示范】(对照以下范例的节奏/密度/句式/语气写作。严禁复述范例原文,只学其风格)",
             *[f"  ✓ {s}" for s in (ex.get("good") or [])],
             *[f"  ✗ {s}(避免)" for s in (ex.get("bad") or [])], ""]
            if (ex.get("good") or ex.get("bad")) else [])

    secrets = ctx.get("reader_disclosed_secrets") or []
    sec_block = (["【读者此刻(本章时点)已知的信息——只能用这些,不得越界】"
                  + json.dumps(secrets, ensure_ascii=False, indent=2),
                  "上面含到本章才解封的揭示(若有)。揭示章可写明已解封的真相;但**未在列表里的角色隐藏身世/动机/来历——一律不得临场编造**(种子没编码的揭示,writer 凭空编了必和他章冲突)。", ""]
                 if secrets else [])

    multi_block = ([f"【多 beat 章,共 {len(beats)} 个 beat】每个 beat 的内容块**前面**单独起一行写标记 "
                    f"@@beat:<beat_id>@@(beat_id 见各 beat 契约),按契约顺序。这样系统才能把段落正确归属到对应 beat。",
                    "beat 契约(注意每个的 beat_id):" + json.dumps(beats, ensure_ascii=False, indent=2), ""]
                   if multi else [])

    lo, hi = word_target if word_target else (3000, 5000)

    feedback = (["【重写反馈·上版未过结构门禁,这些问题必须修】" + violations_feedback, ""]
                if violations_feedback else [])

    parts = [
        f"# 章节写作员 | 本章=第{chapter_global}章 卷={volume_id}",
        "boot context(beat 契约/正典/指纹/指令,必须遵守):",
        json.dumps(ctx, ensure_ascii=False, indent=2),
        "",
        *prev, *canon, *directive, *demo, *sec_block,
        HYGIENE_RULES,
        *multi_block,
        *feedback,
        "【任务·单次产出】按 beat_contracts 写整章正文。视角符合 pov,推进每个 beat 的叙事目的。"
        f"字数 {lo}–{hi}。第一段必须是小说正文(人物/场景/动作),严禁作者旁白/开场白(\"我将/下面/本章将撰写\"等自述语会被系统剥除)。",
        "**只输出整章正文本身**:段落间空行分隔,多 beat 章按上面 @@beat 标记;不写标题行,不裹 markdown 围栏,不写任何解释/JSON/思考过程。",
    ]
    return "\n".join(p for p in parts if p is not None)


def editor_prompt(ctx: dict, chapter_global: int, volume_id: int, current_prose: str,
                  word_target: tuple, violations_feedback: str = "") -> str:
    """构造 editor(revise)单次修订 prompt。

    移植自 .js editorPrompt 的【创意内容】(正典/指令/范例/hygiene/两相协议),去掉 tool-loop——
    runner 里 editor 是单次 LLM 出**修订后整章正文**,commit/L2/迭代由 Python 图管。
    violations_feedback: 上版 L2 违规(空=write 已过结构,本轮做文风收敛相2)。
    """
    chars = ctx.get("characters") or []
    canon = ([f"【角色正典·必须严格遵守】代词/性别/称呼不得擅改"
              f"(如 {chars[0]['name']}={chars[0].get('pronoun')}):",
              json.dumps([{"name": c.get("name"), "pronoun": c.get("pronoun"),
                           "gender": c.get("gender"), "role": c.get("role")}
                          for c in chars], ensure_ascii=False, indent=2), ""]
             if chars else [])

    directive = (["【文风指令·定性要求(高于统计指纹,必须贯彻)】", ctx["style_directive"], ""]
                 if ctx.get("style_directive") else [])

    ex = ctx.get("style_examples") or {}
    demo = (["【风格示范】(对照以下范例的节奏/密度/句式/语气。严禁复述范例原文,只学其风格)",
             *[f"  ✓ {s}" for s in (ex.get("good") or [])],
             *[f"  ✗ {s}(避免)" for s in (ex.get("bad") or [])], ""]
            if (ex.get("good") or ex.get("bad")) else [])

    lo, hi = word_target if word_target else (3000, 5000)

    fb = (["【修订反馈·上版未过结构门禁,这些问题必须修】" + violations_feedback, ""]
          if violations_feedback else [])

    parts = [
        f"# 章节修订员 | 本章=第{chapter_global}章 卷={volume_id}",
        "boot context(beat 契约/正典/指纹/指令,必须遵守):",
        json.dumps(ctx, ensure_ascii=False, indent=2),
        "",
        *canon, *directive, *demo,
        HYGIENE_RULES,
        *fb,
        "【当前正文·在此基础上修订(累进接受,不丢叙事进展与已揭示信息)】",
        current_prose,
        "",
        "【任务·单次产出修订版整章正文】",
        "1. 相1(正确性优先):若结构门禁未过——字数不足→在剧情骨架上整章扩写(增场景细节/感官/心理/对白;"
        "禁灌水、禁重复、禁堆砌形容词);beat 违规→修正归属。务必让结构(字数+beat)过关。",
        "2. 相2(文风,advisory):结构过后做最小改动的文风收敛——删非必要破折号→换句号断句、"
        "改\"不是A是B\"句式、减过密比喻、段落短促视角克制。",
        f"字数 {lo}–{hi}。整章正文第一段必须是小说正文(人物/场景/动作),严禁作者旁白/开场白。",
        "**只输出修订后的整章正文本身**:段落间空行分隔,多 beat 章按 @@beat:<beat_id>@@ 标记;"
        "不写标题行,不裹 markdown 围栏,不写任何解释/JSON/思考过程。",
    ]
    return "\n".join(p for p in parts if p is not None)
