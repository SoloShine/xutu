"""
Novel Knowledge Graph MVP
主流程：构建图谱 → 一致性检查 → 基于图谱的续写演示
"""

from .graph import NovelKG
from .extractor import build_graph
import json


def main():
    print("=" * 60)
    print("Novel Knowledge Graph MVP")
    print("用《间隙》验证：图谱能否优于全文塞prompt")
    print("=" * 60)

    kg = NovelKG()

    # Step 1: 构建图谱
    print("\n--- Step 1: 构建知识图谱 ---")
    build_graph(kg)

    # Step 2: 查看图谱统计
    print("\n--- Step 2: 图谱统计 ---")
    stats = kg.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Step 3: 演示图谱查询 - 获取写第11章时的上下文
    print("\n--- Step 3: 图谱查询演示（第11章上下文）---")
    ctx = kg.get_context_for_chapter(11)
    print(f"  时间段: {[t['label'] for t in ctx['time_periods']]}")
    print(f"  前一章事件数: {len(ctx['prev_events'])}")
    for e in ctx['prev_events']:
        print(f"    - [{e.get('type', '?')}] {e.get('title', '?')}")
    print(f"  涉及人物: {[c['name'] for c in ctx['characters']]}")
    print(f"  核心地点: {[l['name'] for l in ctx['locations']]}")
    print(f"  主题线: {[t['name'] for t in ctx['themes']]}")

    # Step 4: 一致性检查
    print("\n--- Step 4: 一致性检查 ---")
    issues = kg.check_consistency()
    if issues:
        for iss in issues:
            print(f"  [{iss['severity'].upper()}] {iss['type']}: {iss['detail']}")
    else:
        print("  未检测到一致性问题")

    # Step 5: 演示基于图谱的续写prompt构建
    print("\n--- Step 5: 基于图谱的续写Prompt（对比演示）---")

    # 传统方式：把全文塞进去
    print("\n  [传统方式] 需要把12章约35000字全文放入prompt")
    print("  问题: 上下文窗口可能装不下，即使装得下，信息密度低")

    # 图谱方式：只拉取相关子图
    context_for_13 = kg.get_context_for_chapter(13)  # 假设写第13章
    prompt_context = build_writing_prompt(context_for_13, chapter=13)
    print(f"\n  [图谱方式] 构建的prompt上下文约 {len(prompt_context)} 字")
    print("  优势: 只包含结构化的关键信息，不浪费token")
    print("\n  --- Prompt预览 ---")
    print(prompt_context[:800])
    print("  ...（截断）")

    # Step 6: 验证总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    print(f"  图谱节点数: {stats['characters'] + stats['locations'] + stats['events'] + stats['themes']}")
    print(f"  图谱关系数: {stats['relationships']}")
    print(f"  一致性问题: {len(issues)} 个")
    print(f"  图谱上下文: ~{len(prompt_context)} 字 (vs 全文 ~35000 字)")
    print(f"  信息压缩比: ~{35000 // max(len(prompt_context), 1)}:1")
    print()
    print("  核心假设验证:")
    print("  [OK] 故事可以被结构化为知识图谱")
    print("  [OK] 图谱查询能提供精准上下文（信息压缩比远大于1）")
    print("  [OK] 一致性检查可以在图谱上运行")
    print("  [  ] 续写质量对比（需要接入LLM后验证）")

    kg.close()


def build_writing_prompt(context, chapter, language=None, config=None):
    """基于图谱上下文构建续写prompt"""
    lines = []

    # 章节情节弧线（放在最前面，让LLM先理解叙事方向）
    if context.get("chapter_arc"):
        arc = context["chapter_arc"][0]
        lines.append(f"【本章叙事目的】{arc.get('purpose', '')}")
        if arc.get("scenes"):
            lines.append(f"【场景序列】{arc['scenes']}")
        if arc.get("ending"):
            lines.append(f"【结尾锚点】{arc['ending']}")
        if arc.get("gap_note"):
            lines.append(f"【间隙处理】{arc['gap_note']}")

        # 叙事结构指导（硬约束，与风格指南同级别）
        structure_type = arc.get("structure_type", "linear")
        if structure_type and structure_type != "linear":
            lines.append(f"【叙事结构：{structure_type}】")
            if structure_type == "flashback":
                lines.append("  本章包含回忆闪回段落。用感官触发（气味、声音、触感）无缝切换时间。")
                lines.append("  闪回通过物理感官自然过渡，而非直述'他想起了'、'回忆涌上心头'等宣告句。")
                lines.append("  闪回段落必须有独立场景（不同于主时间线的地点或人物状态），不是简单的内心独白。")
            elif structure_type == "intercut":
                lines.append("  本章采用交叉剪辑：至少两条时间线交替出现。")
                lines.append("  不同时间线之间用平行意象或感官呼应连接，不要用分隔线或小标题。")
                lines.append("  每条时间线至少出现2次切换，不能只是一头一尾的简单闪回。")
            elif structure_type == "parallel":
                lines.append("  本章采用平行叙事：不同地点的事件同步推进，展示因果或对比关系。")
                lines.append("  平行场景之间要有结构上的对称（类似的开头或结尾动作），不是随意跳转。")
            time_jumps_str = arc.get("time_jumps")
            if time_jumps_str:
                try:
                    time_jumps = json.loads(time_jumps_str) if isinstance(time_jumps_str, str) else time_jumps_str
                    if time_jumps:
                        lines.append("  时间跳转安排：")
                        for tj in time_jumps:
                            lines.append(f"    - {tj.get('position', '')}: 跳至「{tj.get('target', '')}」({tj.get('type', '')})")
                except (json.JSONDecodeError, TypeError):
                    pass

        # 叙事节奏指导
        rhythm = arc.get("rhythm", "")
        if rhythm:
            rhythm_guide = {
                "tight": "【叙事节奏：紧凑】本章以短句密集推进，场景快速切换，信息密度高。段落间不留呼吸空间。适合追逐、紧迫、倒计时场景。",
                "ascending": "【叙事节奏：递进】本章从缓慢开始，逐步加速。前半段中等句长建立氛围，后半段短句密集推向高潮。像水面下的暗流逐渐浮出。",
                "descending": "【叙事节奏：递减】本章从激烈开始，逐步放慢。开篇短促有力，中段放缓观察，结尾安静留下余韵。适合高潮后的沉淀和发现。",
                "mixed": "【叙事节奏：混合】本章节奏自由变化，快慢交替。允许突然加速和突然停顿。用节奏的落差制造阅读体验的起伏。",
            }
            if rhythm in rhythm_guide:
                lines.append(rhythm_guide[rhythm])
        lines.append("")

    # 时间段
    if context.get("time_periods"):
        tp = context["time_periods"][0]
        lines.append(f"【时间段】{tp.get('label', '')} ({tp.get('years', '')})")
        lines.append(f"【主题】{tp.get('theme', '')}")
        lines.append(f"【主角年龄】{tp.get('age_range', '')}")
        lines.append("")

    # 前一章事件（衔接用）
    if context.get("prev_events"):
        lines.append("【前一章事件】")
        for e in context["prev_events"]:
            gap_mark = " [间隙]" if e.get("is_gap") else ""
            lines.append(f"  - {e.get('title', '')}{gap_mark}: {e.get('detail', '')}")
        lines.append("")

    # 前一章正文片段（感官/风格延续）
    if context.get("prev_chapter_text"):
        lines.append("【前一章结尾（保持感官和风格延续）】")
        lines.append(context["prev_chapter_text"])
        lines.append("")

    # 人物状态 + 人名硬约束
    if context.get("characters"):
        lines.append("【人物状态】")
        for c in context["characters"]:
            lines.append(f"  {c['name']}({c.get('role', '')}): {c.get('personality', '')}")
            if c.get("gap_relation"):
                lines.append(f"    间隙关系: {c['gap_relation']}")
        char_names = "、".join(c["name"] for c in context["characters"])
        lines.append(f"  现有人物：{char_names}")
        lines.append("")

    # 地点
    if context.get("locations"):
        lines.append("【核心地点】")
        for l in context["locations"]:
            lines.append(f"  {l['name']}: {l.get('description', '')} (间隙密度: {l.get('gap_density', 0)})")
        lines.append("")

    # 主题线
    if context.get("themes"):
        lines.append("【主题线】")
        for t in context["themes"]:
            lines.append(f"  {t['name']}: {t.get('description', '')} ({t.get('chapters', '')}章)")
            if t.get("evolution"):
                lines.append(f"    演变: {t['evolution']}")
        lines.append("")

    # 风格指南
    if context.get("style_guides"):
        lines.append("【叙事风格】")
        for sg in context["style_guides"]:
            lines.append(f"  - {sg['rule']}")
        lines.append("")

    # 核心意象
    if context.get("motifs"):
        lines.append("【核心意象】")
        for m in context["motifs"]:
            lines.append(f"  {m['name']}: {m.get('meaning', '')}")
            lines.append(f"    演变: {m.get('evolution', '')}")
        lines.append("")

    # 悬念线
    if context.get("suspense_threads"):
        lines.append("【悬念线】")
        for st in context["suspense_threads"]:
            importance_note = " ★本章应考虑推进或解决" if st.get("importance") == "high" else ""
            lines.append(f"  [{st.get('importance', '?')}] {st.get('id', '')}: {st.get('content', '')} [{st.get('status', '')}]{importance_note}")
        lines.append("")

    # 大纲条目（硬约束）
    if context.get("outline_entry"):
        oe = context["outline_entry"]
        lines.append("【本章大纲约束】")
        lines.append(f"  目的: {oe.get('purpose', '')}")
        if oe.get("key_events"):
            lines.append(f"  关键事件: {oe['key_events']}")
        if oe.get("threads_to_plant"):
            lines.append(f"  需埋下: {oe['threads_to_plant']}")
        if oe.get("threads_to_resolve"):
            lines.append(f"  需解决: {oe['threads_to_resolve']}")
        if oe.get("structure_hint"):
            lines.append(f"  结构提示: {oe['structure_hint']}")
        lines.append("")

    lines.append(f"【任务】根据以上结构化上下文，续写第{chapter}章。")
    lines.append("保持人物性格一致性，维护情节逻辑，体现主题递进。")
    lines.append("")
    lines.append(f"【格式要求】")
    lines.append(f"- 第一行写章节名，格式为：第{chapter}章 章节名（章节名要贴合本章内容，2-6个字，有画面感）")
    lines.append(f"- 章节名后空一行，然后开始正文")
    lines.append("")
    lines.append("【绝对禁止】")
    lines.append('- 禁止使用「不是X，是Y」或「不是X而是Y」句式。这是最严重的文体问题。')
    lines.append("  错误示例：不是不想睡，是睡不着 / 不是热，是某种灼烧感 / 不是恐惧，而是兴奋")
    lines.append("  正确做法：直接写正面描述。睡不着就是睡不着，灼烧感就是灼烧感。不需要否定前置。")
    lines.append("- 如果想强调对比，用冒号、破折号或直接转折，不要用否定前缀。")
    lines.append("")
    lines.append("【场景展开要求】")
    lines.append("- 每个场景至少包含：感官细节（视觉/听觉/触觉/嗅觉）、人物动作、环境变化")
    lines.append("- 不要只写情节推进，要让读者'看到'场景——光线、温度、声音、质感")
    lines.append("- 对话前后加环境反应（天气变化、动物行为、其他人的动作），不要孤立对话")
    lines.append("- 过渡场景也要有细节：路途中的景物、时间的流逝、季节变化")
    writing_cfg = (config or {}).get("writing", {})
    min_words = writing_cfg.get("min_words", 2500)
    max_words = writing_cfg.get("max_words", 3500)
    min_scene = writing_cfg.get("min_words_per_scene", 600)
    lines.append(f"- 【重要】篇幅目标：本章目标{min_words}-{max_words}字。每个场景至少{min_scene}字。宁可多写细节也不能压缩跳过")

    if language:
        lang_map = {
            "繁體中文": "繁體中文",
            "简体中文": "简体中文",
        }
        lang_label = lang_map.get(language, language)
        lines.append(f"- 语言：使用{lang_label}书写，人物名和地名保持与上下文一致")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
