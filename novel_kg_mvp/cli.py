"""
小说知识图谱 CLI — 智能体工作流编排层

用法:
  python cli.py --project <项目名> init                 # 初始化项目（清空该项目图谱）
  python cli.py --project <项目名> add character        # 交互式录入人物
  python cli.py --project <项目名> add location         # 交互式录入地点
  python cli.py --project <项目名> add style            # 录入风格规则
  python cli.py --project <项目名> add motif            # 录入意象
  python cli.py --project <项目名> add theme            # 录入主题
  python cli.py --project <项目名> add arc <章号>       # 录入/推演章节弧线
  python cli.py --project <项目名> extract <章号> <文件>
  python cli.py --project <项目名> writeback <章号> <JSON文件>
  python cli.py --project <项目名> derive <章号>        # 推演章节弧线
  python cli.py --project <项目名> write <章号>         # 构建续写prompt
  python cli.py --project <项目名> status               # 图谱统计
  python cli.py --project <项目名> loop <章号> <文件>   # 全闭环
"""

import sys
import io
import json
import os

# Windows GBK fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

import click
import yaml
from graph import NovelKG
from mine import (
    build_extraction_prompt, detect_conflicts,
    write_extraction_to_graph, clear_chapter_data
)
from prompts import EXTRACTION_PROMPT, ARC_DERIVATION_PROMPT
from main import build_writing_prompt
from llm import extract_from_text, derive_arc, generate_chapter, generate_world, generate_outline, prequery_plan
from validators import validate_chapter as run_validation, apply_name_fixes


PROJECTS_DIR = "projects"


def ensure_project_dir(project):
    """确保项目目录存在"""
    pdir = os.path.join(PROJECTS_DIR, project)
    for sub in ["chapters", "extractions", "prompts", "output"]:
        os.makedirs(os.path.join(pdir, sub), exist_ok=True)
    # 如果没有 project.yaml，创建一个最小的
    meta = os.path.join(pdir, "project.yaml")
    if not os.path.exists(meta):
        with open(meta, "w", encoding="utf-8") as f:
            yaml.dump({"name": project, "identifier": project}, f,
                      allow_unicode=True)
    return pdir


def project_path(project, *parts):
    """获取项目下的文件路径"""
    return os.path.join(PROJECTS_DIR, project, *parts)


def get_project_meta(project):
    """读取项目元信息"""
    meta_file = project_path(project, "project.yaml")
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_kg(project):
    """获取图谱连接"""
    return NovelKG(project=project)


def confirm(prompt_text):
    """确认提示"""
    return click.confirm(f"  {prompt_text}", default=False)


def prompt_input(label, default=""):
    """带默认值的输入"""
    return click.prompt(f"  {label}", default=default, show_default=bool(default))


# ========== 初始化 ==========

@click.group()
@click.option("--project", "-p", required=True, help="项目标识（如 jianxi, sheng_si_chang）")
@click.pass_context
def cli(ctx, project):
    """小说知识图谱 CLI"""
    ctx.ensure_object(dict)
    ctx.obj["project"] = project
    ensure_project_dir(project)


# ========== 初始化 ==========

@cli.command()
@click.pass_context
def init(ctx):
    """初始化项目（清空该项目图谱数据）"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    click.echo(f"将清空项目 '{project}' 的图谱数据（不影响其他项目）。")
    if confirm("确认初始化？"):
        kg.clear_project()
        click.echo("[OK] 图谱已清空。使用 add 命令录入数据。")
    else:
        click.echo("取消。")
    kg.close()


# ========== 世界观初始化 ==========

@cli.command()
@click.option("--direction", "-d", default="", help="创作方向描述")
@click.option("--auto", is_flag=True, help="自动模式：不确认直接写入图谱")
@click.pass_context
def setup(ctx, direction, auto):
    """LLM生成世界观设定（风格/人物/地点/主题/时间段 + 第1章arc）"""
    project = ctx.obj["project"]
    kg = get_kg(project)

    if not direction:
        direction = click.prompt("  请输入创作方向", default="一部关于日常生活的文学短篇")

    click.echo(f"创作方向: {direction}")
    click.echo("正在调用LLM生成世界观...")

    try:
        world = generate_world(direction)
    except Exception as e:
        click.echo(f"[ERROR] 世界观生成失败: {e}")
        kg.close()
        return

    # 保存世界观设定
    world_file = project_path(project, "world_setup.json")
    with open(world_file, "w", encoding="utf-8") as f:
        json.dump(world, f, ensure_ascii=False, indent=2)
    click.echo(f"世界观设定已保存: {world_file}")

    # 展示设定
    click.echo(f"\n{'=' * 40}")
    click.echo(f"标题: {world.get('title', '')}")
    click.echo(f"核心设定: {world.get('premise', '')}")
    click.echo(f"风格质感: {world.get('style_analysis', '')}")
    click.echo(f"\n风格指南 ({len(world.get('style_guides', []))} 条):")
    for sg in world.get("style_guides", []):
        click.echo(f"  - [{sg['id']}] {sg['rule']}")
    click.echo(f"\n人物 ({len(world.get('characters', []))} 个):")
    for c in world.get("characters", []):
        click.echo(f"  - {c['name']}({c['role']}): {c['personality']}")
    click.echo(f"\n地点 ({len(world.get('locations', []))} 个):")
    for l in world.get("locations", []):
        click.echo(f"  - {l['name']}({l.get('type', '')}): {l.get('description', '')}")
    click.echo(f"\n主题 ({len(world.get('themes', []))} 个):")
    for t in world.get("themes", []):
        click.echo(f"  - {t['name']}: {t.get('description', '')} ({t.get('chapters', '')}章)")
    click.echo(f"\n时间段 ({len(world.get('time_periods', []))} 个):")
    for tp in world.get("time_periods", []):
        click.echo(f"  - {tp['label']}: Ch{tp['chapter_start']}-{tp['chapter_end']} ({tp.get('years', '')})")
    first_arc = world.get("first_arc", {})
    click.echo(f"\n第1章弧线:")
    click.echo(f"  目的: {first_arc.get('purpose', '')}")
    click.echo(f"  场景: {first_arc.get('scenes', '')}")
    click.echo(f"  结尾: {first_arc.get('ending', '')}")
    click.echo(f"{'=' * 40}")

    # 写入图谱
    if auto or confirm("确认写入图谱？"):
        # 风格指南
        for sg in world.get("style_guides", []):
            kg.add_style_guide(sg["id"], rule=sg["rule"])
        click.echo(f"  风格指南: {len(world.get('style_guides', []))} 条")

        # 人物
        for c in world.get("characters", []):
            kg.add_character(c["name"], role=c.get("role", ""),
                             personality=c.get("personality", ""))
        click.echo(f"  人物: {len(world.get('characters', []))} 个")

        # 地点
        for l in world.get("locations", []):
            kg.add_location(l["name"], type=l.get("type", ""),
                            description=l.get("description", ""))
        click.echo(f"  地点: {len(world.get('locations', []))} 个")

        # 主题
        for t in world.get("themes", []):
            kg.add_theme(t["name"], description=t.get("description", ""),
                         chapters=t.get("chapters", ""))
        click.echo(f"  主题: {len(world.get('themes', []))} 个")

        # 时间段
        for tp in world.get("time_periods", []):
            kg.add_time_period(tp["label"],
                               chapter_start=tp["chapter_start"],
                               chapter_end=tp["chapter_end"],
                               years=tp.get("years", ""),
                               theme=tp.get("theme", ""))
        click.echo(f"  时间段: {len(world.get('time_periods', []))} 个")

        # 第1章arc
        if first_arc:
            kg.add_chapter_arc(1, **{k: v for k, v in first_arc.items()
                                     if k in ("purpose", "scenes", "ending", "gap_note")})
            click.echo(f"  第1章弧线: 已写入")

        # 更新project.yaml
        meta_file = project_path(project, "project.yaml")
        meta = get_project_meta(project)
        meta["name"] = world.get("title", project)
        meta["language"] = "简体中文"
        meta["description"] = world.get("premise", "")
        meta["chapters"] = 6
        with open(meta_file, "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True)

        click.echo("[OK] 世界观已写入图谱。可使用 gen-outline --auto 生成大纲。")
    else:
        click.echo("取消写入。世界观已保存到文件，可手动录入。")

    kg.close()


# ========== 大纲生成 ==========

@cli.command("gen-outline")
@click.option("--auto", is_flag=True, help="自动生成并写入图谱")
@click.option("--chapters", "-n", default=6, type=int, help="总章数")
@click.pass_context
def gen_outline_cmd(ctx, auto, chapters):
    """LLM生成全局大纲"""
    project = ctx.obj["project"]
    kg = get_kg(project)

    world_file = project_path(project, "world_setup.json")
    if not os.path.exists(world_file):
        click.echo("[ERROR] 未找到世界观设定，请先运行 setup 命令")
        kg.close()
        return

    with open(world_file, "r", encoding="utf-8") as f:
        world = json.load(f)

    click.echo("正在调用LLM生成大纲...")
    try:
        outline = generate_outline(world, chapters)
    except Exception as e:
        click.echo(f"[ERROR] 大纲生成失败: {e}")
        kg.close()
        return

    # 保存
    outline_file = project_path(project, "outline.json")
    with open(outline_file, "w", encoding="utf-8") as f:
        json.dump(outline, f, ensure_ascii=False, indent=2)

    summary = outline.get("narrative_arc_summary", "")
    if summary:
        click.echo(f"\n全局叙事弧: {summary}")

    # 展示
    for entry in outline.get("outline", []):
        ch = entry.get("chapter", "?")
        click.echo(f"\n第{ch}章:")
        click.echo(f"  目的: {entry.get('purpose', '')}")
        click.echo(f"  关键事件: {entry.get('key_events', '')}")
        if entry.get("threads_to_plant"):
            click.echo(f"  埋下: {entry['threads_to_plant']}")
        if entry.get("threads_to_resolve"):
            click.echo(f"  解决: {entry['threads_to_resolve']}")
        if entry.get("structure_hint"):
            click.echo(f"  结构: {entry['structure_hint']}")

    # 写入图谱
    if auto or confirm("确认写入图谱？"):
        # 存储全局叙事弧概要到project.yaml
        if summary:
            meta_file = project_path(project, "project.yaml")
            meta = get_project_meta(project)
            meta["narrative_arc_summary"] = summary
            with open(meta_file, "w", encoding="utf-8") as f:
                yaml.dump(meta, f, allow_unicode=True)

        for entry in outline.get("outline", []):
            ch = entry.get("chapter")
            if not ch:
                continue
            # 先创建悬念线节点
            for i, tp in enumerate(entry.get("threads_to_plant", [])):
                if isinstance(tp, str) and tp.strip():
                    tid = f"ST{ch:02d}_{i+1:02d}"
                    kg.add_suspense_thread(tid, content=tp.strip(),
                                           planted_chapter=ch, importance="medium",
                                           thread_type="foreshadowing", status="planted")
            # 写入大纲条目
            kg.add_outline_entry(
                ch,
                purpose=entry.get("purpose", ""),
                key_events=entry.get("key_events", ""),
                threads_to_plant=str(entry.get("threads_to_plant", [])),
                threads_to_resolve=str(entry.get("threads_to_resolve", [])),
                structure_hint=entry.get("structure_hint", "")
            )
        click.echo("[OK] 大纲已写入图谱")
    else:
        click.echo("取消写入。大纲已保存到文件。")

    kg.close()


# ========== 添加节点 ==========

@cli.group()
def add():
    """添加图谱节点"""
    pass


@add.command()
@click.pass_context
def character(ctx):
    """交互式录入人物"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    name = prompt_input("人物名")
    role = prompt_input("角色（如：主角/配角/反派）")
    personality = prompt_input("性格描述")
    gap_relation = prompt_input("特殊关系（如：间隙相关，留空跳过）", "")

    kg.add_character(name, role=role, personality=personality,
                     gap_relation=gap_relation)
    click.echo(f"[OK] 已添加人物: {name}")
    kg.close()


@add.command()
@click.pass_context
def location(ctx):
    """交互式录入地点"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    name = prompt_input("地点名")
    loc_type = prompt_input("类型（如：村落/城市/自然）")
    description = prompt_input("描述")

    kg.add_location(name, type=loc_type, description=description,
                    gap_density=0)
    click.echo(f"[OK] 已添加地点: {name}")
    kg.close()


@add.command()
@click.pass_context
def style(ctx):
    """录入风格规则"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    guide_id = prompt_input("规则ID（如：narrative_voice）")
    rule = prompt_input("规则内容")

    kg.add_style_guide(guide_id, rule=rule)
    click.echo(f"[OK] 已添加风格规则: {guide_id}")
    kg.close()


@add.command()
@click.pass_context
def motif(ctx):
    """录入意象"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    name = prompt_input("意象名")
    meaning = prompt_input("含义")
    evolution = prompt_input("演变线")

    kg.add_motif(name, meaning=meaning, evolution=evolution)
    click.echo(f"[OK] 已添加意象: {name}")
    kg.close()


@add.command()
@click.pass_context
def theme(ctx):
    """录入主题"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    name = prompt_input("主题名")
    description = prompt_input("描述")
    chapters = prompt_input("涉及章节（如：1-4）")

    kg.add_theme(name, description=description, chapters=chapters)
    click.echo(f"[OK] 已添加主题: {name}")
    kg.close()


@add.command("arc")
@click.argument("chapter", type=int)
@click.pass_context
def add_arc(ctx, chapter):
    """录入章节弧线"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    purpose = prompt_input("叙事目的")
    scenes = prompt_input("场景序列（用 → 连接）")
    ending = prompt_input("结尾锚点")
    gap_note = prompt_input("特殊处理说明（留空跳过）", "")

    kg.add_chapter_arc(chapter, purpose=purpose, scenes=scenes,
                       ending=ending, gap_note=gap_note)
    click.echo(f"[OK] 已添加第{chapter}章弧线")
    kg.close()


@add.command("timeperiod")
@click.pass_context
def add_timeperiod(ctx):
    """录入时间段"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    label = prompt_input("时间段名（如：第一阶段：惯性）")
    ch_start = click.prompt("  起始章", type=int)
    ch_end = click.prompt("  结束章", type=int)
    years = prompt_input("年份")
    theme = prompt_input("主题")

    kg.add_time_period(label, chapter_start=ch_start, chapter_end=ch_end,
                       years=years, theme=theme)
    click.echo(f"[OK] 已添加时间段: {label}")
    kg.close()


@add.command("relation")
@click.pass_context
def add_relation(ctx):
    """录入人物关系"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    click.echo("  可用关系类型: SPOUSE_OF, PARENT_OF, COMRADE_WITH, FRIEND_OF, BOND_WITH, SON_OF, TAUGHT_BY")
    rel_type = prompt_input("关系类型")
    char_a = prompt_input("人物A")
    char_b = prompt_input("人物B")
    description = prompt_input("关系描述（留空跳过）", "")

    kg.add_relation("Character", "name", char_a, rel_type,
                    "Character", "name", char_b, description=description)
    click.echo(f"[OK] 已添加关系: {char_a} -{rel_type}-> {char_b}")
    kg.close()


@add.command("thread")
@click.option("--thread-id", "-t", required=True, help="线索ID（如ST01）")
@click.option("--content", "-c", required=True, help="悬念内容")
@click.option("--importance", "-i", type=click.Choice(["high", "medium", "low"]), default="medium")
@click.option("--thread-type", type=click.Choice(["foreshadowing", "clue", "mystery", "character_arc"]), default="foreshadowing")
@click.option("--planted-chapter", type=int, required=True, help="埋下章节号")
@click.pass_context
def add_thread(ctx, thread_id, content, importance, thread_type, planted_chapter):
    """录入悬念线"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    kg.add_suspense_thread(thread_id, content=content, importance=importance,
                           thread_type=thread_type, planted_chapter=planted_chapter,
                           status="planted")
    click.echo(f"[OK] 已添加悬念线: {thread_id} - {content}")
    kg.close()


@add.command("outline")
@click.argument("chapter", type=int)
@click.pass_context
def add_outline(ctx, chapter):
    """交互式录入章节大纲"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    purpose = prompt_input("本章目的")
    key_events = prompt_input("关键事件（分号分隔）")
    threads_to_plant = prompt_input("需埋下的悬念（逗号分隔）", "")
    threads_to_resolve = prompt_input("需解决的悬念（逗号分隔）", "")
    structure_hint = prompt_input("结构提示（linear/flashback/intercut/parallel）", "")

    kg.add_outline_entry(chapter, purpose=purpose, key_events=key_events,
                         threads_to_plant=threads_to_plant,
                         threads_to_resolve=threads_to_resolve,
                         structure_hint=structure_hint)
    click.echo(f"[OK] 已添加第{chapter}章大纲")
    kg.close()


# ========== 提取 ==========

@cli.command()
@click.argument("chapter", type=int)
@click.argument("text_file", type=click.Path(exists=True))
@click.option("--skip-conflicts/--no-skip-conflicts", default=True,
              help="跳过冲突项")
@click.option("--auto", is_flag=True, help="自动调用LLM提取并写入图谱")
@click.pass_context
def extract(ctx, chapter, text_file, skip_conflicts, auto):
    """从章节文本提取结构化数据"""
    project = ctx.obj["project"]
    kg = get_kg(project)

    # 1. 读取文本
    with open(text_file, "r", encoding="utf-8") as f:
        text = f.read()
    click.echo(f"已读取文本: {len(text)} 字")

    # 2. 构建提取prompt
    characters = kg.get_all_characters()
    char_list = "\n".join(f"  - {c['name']}({c.get('role', '')})" for c in characters)
    threads = kg.get_unresolved_threads(chapter + 1)
    threads_str = "\n".join(
        f"  - {t['id']}: {t.get('content', '')} [{t.get('status', '')}]"
        for t in threads
    ) if threads else "  （无）"
    prompt = EXTRACTION_PROMPT.format(
        characters=char_list,
        suspense_threads=threads_str,
        chapter=chapter,
        chapter_text=text
    )

    # 3. 保存prompt
    prompt_file = project_path(project, "prompts", f"extraction_ch{chapter}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    click.echo(f"提取prompt已保存: {prompt_file}")

    # 4. 自动模式：调用LLM + 写回
    if auto:
        try:
            extracted = extract_from_text(prompt)
        except Exception as e:
            click.echo(f"[ERROR] LLM提取失败: {e}")
            kg.close()
            return

        # 保存提取结果
        json_file = project_path(project, "extractions", f"extraction_ch{chapter}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)
        click.echo(f"提取结果已保存: {json_file}")

        # 冲突检测 + 写回
        conflicts = detect_conflicts(kg, extracted)
        if conflicts:
            click.echo(f"检测到 {len(conflicts)} 个冲突:")
            for c in conflicts:
                icon = "!!!" if c["severity"] == "high" else " ! "
                click.echo(f"  [{icon}] {c['type']}: {c['detail'][:60]}")

        report = write_extraction_to_graph(kg, chapter, extracted,
                                           skip_conflicts=skip_conflicts)
        click.echo(f"写入完成: 事件={report['stats']['events']} "
                   f"关系={report['stats']['relations']} "
                   f"新地点={report['stats']['locations']} "
                   f"冲突跳过={report['stats']['conflicts']}")
    else:
        click.echo("手动模式：请将prompt发送给LLM，将返回的JSON保存后使用 writeback 命令写入。")

    kg.close()


@cli.command()
@click.argument("chapter", type=int)
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--skip-conflicts/--no-skip-conflicts", default=True)
@click.option("--clear/--no-clear", default=False, help="写入前清除该章已有数据")
@click.pass_context
def writeback(ctx, chapter, json_file, skip_conflicts, clear):
    """将提取结果（JSON）写入图谱"""
    project = ctx.obj["project"]
    kg = get_kg(project)

    with open(json_file, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    # 冲突检测
    click.echo("\n--- 冲突检测 ---")
    conflicts = detect_conflicts(kg, extracted)
    if conflicts:
        for c in conflicts:
            icon = "!!!" if c["severity"] == "high" else " ! "
            click.echo(f"  [{icon}] [{c['severity']}] {c['type']}: {c['detail']}")
        click.echo(f"\n  共 {len(conflicts)} 个冲突")
    else:
        click.echo("  无冲突")

    # 可选清除
    if clear:
        if confirm(f"确认清除第{chapter}章已有数据？"):
            clear_chapter_data(kg, chapter)

    # 写入
    if confirm("确认写入图谱？"):
        report = write_extraction_to_graph(kg, chapter, extracted,
                                           skip_conflicts=skip_conflicts)
        click.echo(f"\n--- 写入报告 ---")
        click.echo(f"  事件: {report['stats']['events']}")
        click.echo(f"  关系: {report['stats']['relations']}")
        click.echo(f"  新地点: {report['stats']['locations']}")
        click.echo(f"  冲突跳过: {report['stats']['conflicts']}")
        if report.get("character_updates"):
            click.echo(f"  人物更新（未写入图谱，供作者审核）:")
            for cu in report["character_updates"]:
                click.echo(f"    - {cu.get('name', '')}: {cu.get('content', '')[:60]}...")
        if report.get("notes"):
            click.echo(f"  备注: {report['notes'][:80]}...")
    else:
        click.echo("取消写入。")

    kg.close()


# ========== 推演 ==========

@cli.command()
@click.argument("chapter", type=int)
@click.option("--auto", is_flag=True, help="自动调用LLM推演并写入图谱")
@click.pass_context
def derive(ctx, chapter, auto):
    """推演章节弧线（ChapterArc）"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    ctx_data = kg.get_arc_derivation_context(chapter)

    click.echo(f"\n--- 推演上下文（第{chapter}章）---")
    click.echo(f"  近章弧线: {len(ctx_data['recent_arcs'])} 个")
    for arc in ctx_data["recent_arcs"]:
        click.echo(f"    Ch{arc['chapter']}: {arc.get('purpose', '')}")
    click.echo(f"  近章事件: {len(ctx_data['recent_events'])} 个")
    click.echo(f"  人物: {[c['name'] for c in ctx_data['characters']]}")
    click.echo(f"  主题: {[t['name'] for t in ctx_data['themes']]}")
    click.echo(f"  意象: {[m['name'] for m in ctx_data['motifs']]}")
    if ctx_data["last_event"]:
        click.echo(f"  最后事件: {ctx_data['last_event'].get('title', '')}")

    # 构建推演prompt
    arcs_text = json.dumps(
        [{k: v for k, v in a.items() if k != "chapter"}
         for a in ctx_data["recent_arcs"]], ensure_ascii=False, indent=2
    )
    events_text = json.dumps(
        [{"id": e["id"], "title": e.get("title", ""), "type": e.get("type", ""),
          "detail": e.get("detail", "")}
         for e in ctx_data["recent_events"]], ensure_ascii=False, indent=2
    )
    chars_text = json.dumps(
        [{"name": c["name"], "role": c.get("role", ""),
          "personality": c.get("personality", "")}
         for c in ctx_data["characters"]], ensure_ascii=False, indent=2
    )
    themes_text = json.dumps(
        [{"name": t["name"], "description": t.get("description", ""),
          "chapters": t.get("chapters", "")}
         for t in ctx_data["themes"]], ensure_ascii=False, indent=2
    )
    motifs_text = json.dumps(
        [{"name": m["name"], "meaning": m.get("meaning", ""),
          "evolution": m.get("evolution", "")}
         for m in ctx_data["motifs"]], ensure_ascii=False, indent=2
    )
    last_event_text = json.dumps(
        ctx_data["last_event"], ensure_ascii=False, indent=2
    ) if ctx_data["last_event"] else "无"

    # V10: 大纲和悬念线
    outline_text = json.dumps(ctx_data.get("outline_entry"), ensure_ascii=False, indent=2) if ctx_data.get("outline_entry") else "无"
    threads_text = json.dumps(
        [{"id": t.get("id", ""), "content": t.get("content", ""),
          "status": t.get("status", ""), "importance": t.get("importance", "")}
         for t in ctx_data.get("suspense_threads", [])],
        ensure_ascii=False, indent=2
    ) if ctx_data.get("suspense_threads") else "无"

    prompt = ARC_DERIVATION_PROMPT.format(
        outline_entry=outline_text,
        suspense_threads=threads_text,
        recent_arcs=arcs_text,
        recent_events=events_text,
        characters=chars_text,
        themes=themes_text,
        motifs=motifs_text,
        last_event=last_event_text
    )

    prompt_file = project_path(project, "prompts", f"derivation_ch{chapter}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    click.echo(f"\n推演prompt已保存: {prompt_file}")

    if auto:
        try:
            arc_data = derive_arc(prompt)
        except Exception as e:
            click.echo(f"[ERROR] LLM推演失败: {e}")
            kg.close()
            return

        # 写入图谱（Neo4j不支持嵌套对象，需序列化）
        if arc_data.get("time_jumps") and not isinstance(arc_data["time_jumps"], str):
            arc_data["time_jumps"] = json.dumps(arc_data["time_jumps"], ensure_ascii=False)
        if arc_data.get("thread_plan") and not isinstance(arc_data["thread_plan"], str):
            arc_data["thread_plan"] = json.dumps(arc_data["thread_plan"], ensure_ascii=False)
        kg.add_chapter_arc(chapter, **arc_data)
        click.echo(f"[OK] 第{chapter}章弧线已写入图谱")
        click.echo(f"  目的: {arc_data.get('purpose', '')}")
        click.echo(f"  场景: {arc_data.get('scenes', '')}")
        click.echo(f"  结尾: {arc_data.get('ending', '')}")
    else:
        click.echo("手动模式：将prompt发给LLM后，用 add arc 命令录入结果。")

    kg.close()


# ========== 续写 ==========

@cli.command()
@click.argument("chapter", type=int)
@click.option("--output", "-o", default=None, help="输出文件路径")
@click.option("--auto", is_flag=True, help="自动调用LLM续写章节")
@click.pass_context
def write(ctx, chapter, output, auto):
    """构建续写prompt"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    context = kg.get_context_for_chapter(chapter)

    has_arc = len(context.get("chapter_arc", [])) > 0
    click.echo(f"\n--- 第{chapter}章上下文 ---")
    click.echo(f"  情节弧线: {'有' if has_arc else '无（可用 derive 命令推演）'}")
    click.echo(f"  前一章事件: {len(context.get('prev_events', []))}")
    click.echo(f"  人物: {len(context.get('characters', []))}")
    click.echo(f"  地点: {len(context.get('locations', []))}")
    click.echo(f"  风格规则: {len(context.get('style_guides', []))}")
    click.echo(f"  意象: {len(context.get('motifs', []))}")
    click.echo(f"  悬念线: {len(context.get('suspense_threads', []))}")
    click.echo(f"  大纲: {'有' if context.get('outline_entry') else '无'}")

    prompt = build_writing_prompt(context, chapter, language=get_project_meta(project).get("language"))
    click.echo(f"\nPrompt长度: {len(prompt)} 字")

    out_path = output or project_path(project, "prompts", f"writing_ch{chapter}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    click.echo(f"已保存: {out_path}")

    if auto:
        click.echo("LLM续写中（流式输出）：")
        click.echo("---")
        try:
            generated = generate_chapter(prompt)
        except Exception as e:
            click.echo(f"[ERROR] LLM续写失败: {e}")
            kg.close()
            return

        # 后置校验
        arc = context.get("chapter_arc", [None])
        arc = arc[0] if arc else None
        result = run_validation(generated, context, arc=arc)

        # 自动修复人名
        name_fixes = [v for v in result.violations if v.constraint_type == "character_name" and v.fix]
        if name_fixes:
            generated = apply_name_fixes(generated, name_fixes)
            click.echo(f"  [FIX] 修正 {len(name_fixes)} 个人名")
            for v in name_fixes:
                click.echo(f"    {v.detail} → {v.fix}")

        # 风格/篇幅警告
        for v in result.violations:
            if v.constraint_type in ("style", "length"):
                click.echo(f"  [WARN] {v.detail}")

        # 结构问题重试一次
        struct_errors = [v for v in result.violations if v.constraint_type == "structure" and v.severity == "error"]
        if struct_errors:
            click.echo(f"  [RETRY] 结构: {struct_errors[0].detail}")
            try:
                retry_gen = generate_chapter(prompt)
                retry_result = run_validation(retry_gen, context, arc=arc)
                retry_struct = [v for v in retry_result.violations if v.constraint_type == "structure" and v.severity == "error"]
                if not retry_struct:
                    generated = retry_gen
                    click.echo(f"  [OK] 重试后结构通过")
                else:
                    click.echo(f"  [WARN] 重试仍有结构问题，保留第一次生成")
            except Exception:
                click.echo(f"  [WARN] 重试失败，保留第一次生成")

        output_path = project_path(project, "output", f"ch{chapter}_generated.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"第{chapter}章（LLM续写版）\n\n{generated}")
        click.echo(f"[OK] 续写完成: {output_path} ({len(generated)} 字)")
    else:
        click.echo("手动模式：将prompt发给LLM后，保存续写结果。")

    kg.close()


# ========== 统计 ==========

@cli.command()
@click.pass_context
def status(ctx):
    """显示图谱统计"""
    project = ctx.obj["project"]
    kg = get_kg(project)
    stats = kg.stats()

    click.echo(f"\n--- 图谱统计（项目: {project}）---")
    for k, v in stats.items():
        click.echo(f"  {k}: {v}")

    # 一致性检查
    issues = kg.check_consistency()
    if issues:
        click.echo(f"\n--- 一致性问题 ({len(issues)}) ---")
        for iss in issues:
            click.echo(f"  [{iss['severity']}] {iss['type']}: {iss['detail']}")
    else:
        click.echo("\n  一致性检查通过")

    kg.close()


# ========== 全闭环 ==========

@cli.command()
@click.argument("chapter", type=int)
@click.argument("text_file", type=click.Path(exists=True))
@click.option("--skip-conflicts/--no-skip-conflicts", default=True)
@click.option("--auto", is_flag=True, help="全自动：LLM提取→写回→推演→续写")
@click.pass_context
def loop(ctx, chapter, text_file, skip_conflicts, auto):
    """全闭环：提取前一章文本 → 写回 → 推演本章弧线 → 续写本章

    chapter参数为要生成的章节号，text_file为前一章的文本文件。
    例：loop 2 ch1.txt → 提取ch1 → 推导ch2弧线 → 续写ch2
    """
    project = ctx.obj["project"]
    kg = get_kg(project)
    prev_ch = chapter - 1  # text_file是前一章的文本

    click.echo(f"\n{'=' * 50}")
    click.echo(f"全闭环流程：项目 '{project}' 生成第{chapter}章 {'(自动)' if auto else '(手动)'}")
    click.echo(f"  输入文本：第{prev_ch}章 → 输出：第{chapter}章")
    click.echo(f"{'=' * 50}")

    # Step 1: 提取前一章
    click.echo(f"\n[1/5] 构建提取prompt（第{prev_ch}章）...")
    with open(text_file, "r", encoding="utf-8") as f:
        text = f.read()
    characters = kg.get_all_characters()
    char_list = "\n".join(f"  - {c['name']}({c.get('role', '')})" for c in characters)
    threads = kg.get_unresolved_threads(prev_ch)
    threads_str = "\n".join(
        f"  - {t['id']}: {t.get('content', '')} [{t.get('status', '')}]"
        for t in threads
    ) if threads else "  （无）"
    prompt = EXTRACTION_PROMPT.format(
        characters=char_list, suspense_threads=threads_str,
        chapter=prev_ch, chapter_text=text
    )
    prompt_file = project_path(project, "prompts", f"extraction_ch{prev_ch}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    click.echo(f"  提取prompt: {prompt_file} ({len(prompt)} 字)")

    if auto:
        try:
            extracted = extract_from_text(prompt)
        except Exception as e:
            click.echo(f"  [ERROR] LLM提取失败: {e}")
            kg.close()
            return

        json_file = project_path(project, "extractions", f"extraction_ch{prev_ch}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)
        click.echo(f"  提取结果: {json_file}")
    else:
        # 手动模式：检查是否已有提取结果
        json_file = project_path(project, "extractions", f"extraction_ch{prev_ch}.json")
        if os.path.exists(json_file):
            if confirm(f"发现已有提取结果，是否直接使用？"):
                with open(json_file, "r", encoding="utf-8") as f:
                    extracted = json.load(f)
            else:
                click.echo("  跳过写回。完成提取后重新运行。")
                kg.close()
                return
        else:
            click.echo(f"  未找到提取结果，跳过写回。")
            click.echo("  完成提取后，重新运行此命令。")
            kg.close()
            return

    # Step 2: 冲突检测
    click.echo(f"\n[2/5] 冲突检测...")
    conflicts = detect_conflicts(kg, extracted)
    if conflicts:
        for c in conflicts:
            icon = "!!!" if c["severity"] == "high" else " ! "
            click.echo(f"  [{icon}] {c['type']}: {c['detail'][:60]}")
        click.echo(f"  共 {len(conflicts)} 个冲突")
    else:
        click.echo("  无冲突")

    # Step 3: 写回
    click.echo(f"\n[3/5] 写入图谱（第{prev_ch}章数据）...")
    report = write_extraction_to_graph(kg, prev_ch, extracted,
                                       skip_conflicts=skip_conflicts)
    click.echo(f"  事件:{report['stats']['events']} "
              f"关系:{report['stats']['relations']} "
              f"地点:{report['stats'].get('locations', 0)} "
              f"新人物:{report['stats'].get('characters', 0)}")

    # Step 4: 推演本章弧线
    click.echo(f"\n[4/5] 推演第{chapter}章弧线...")
    ctx_data = kg.get_arc_derivation_context(chapter)
    click.echo(f"  近章弧线: {len(ctx_data['recent_arcs'])} 个, "
              f"近章事件: {len(ctx_data['recent_events'])} 个")

    if auto:
        arcs_text = json.dumps(ctx_data["recent_arcs"], ensure_ascii=False, indent=2)
        events_text = json.dumps(ctx_data["recent_events"], ensure_ascii=False, indent=2)
        chars_text = json.dumps(ctx_data["characters"], ensure_ascii=False, indent=2)
        themes_text = json.dumps(ctx_data["themes"], ensure_ascii=False, indent=2)
        motifs_text = json.dumps(ctx_data["motifs"], ensure_ascii=False, indent=2)
        last_event_text = json.dumps(ctx_data["last_event"], ensure_ascii=False, indent=2) if ctx_data["last_event"] else "无"
        outline_text = json.dumps(ctx_data.get("outline_entry"), ensure_ascii=False, indent=2) if ctx_data.get("outline_entry") else "无"
        threads_text = json.dumps(
            [{"id": t.get("id", ""), "content": t.get("content", ""),
              "status": t.get("status", ""), "importance": t.get("importance", "")}
             for t in ctx_data.get("suspense_threads", [])],
            ensure_ascii=False, indent=2
        ) if ctx_data.get("suspense_threads") else "无"

        derive_prompt = ARC_DERIVATION_PROMPT.format(
            outline_entry=outline_text, suspense_threads=threads_text,
            recent_arcs=arcs_text, recent_events=events_text,
            characters=chars_text, themes=themes_text,
            motifs=motifs_text, last_event=last_event_text
        )
        try:
            arc_data = derive_arc(derive_prompt)
            # Neo4j不支持嵌套对象属性，需序列化为JSON字符串
            if arc_data.get("time_jumps") and not isinstance(arc_data["time_jumps"], str):
                arc_data["time_jumps"] = json.dumps(arc_data["time_jumps"], ensure_ascii=False)
            if arc_data.get("thread_plan") and not isinstance(arc_data["thread_plan"], str):
                arc_data["thread_plan"] = json.dumps(arc_data["thread_plan"], ensure_ascii=False)
            kg.add_chapter_arc(chapter, **arc_data)
            click.echo(f"  推演结果: {arc_data.get('purpose', '')}")
        except Exception as e:
            click.echo(f"  [WARN] 推演失败: {e}，跳过")
    else:
        derive_prompt_file = project_path(project, "prompts", f"derivation_ch{chapter}.txt")
        with open(derive_prompt_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(ctx_data, ensure_ascii=False, indent=2))
        click.echo(f"  推演prompt: {derive_prompt_file}")

    # Step 5: 续写本章
    click.echo(f"\n[5/5] 构建第{chapter}章续写prompt...")
    context = kg.get_context_for_chapter(chapter)
    write_prompt = build_writing_prompt(context, chapter, language=get_project_meta(project).get("language"))
    write_file = project_path(project, "prompts", f"writing_ch{chapter}.txt")
    with open(write_file, "w", encoding="utf-8") as f:
        f.write(write_prompt)
    click.echo(f"  续写prompt: {write_file} ({len(write_prompt)} 字)")

    if auto:
        click.echo("  LLM续写中（流式输出）：")
        click.echo("  ---")
        try:
            generated = generate_chapter(write_prompt)

            # 后置校验
            arc = context.get("chapter_arc", [None])
            arc = arc[0] if arc else None
            result = run_validation(generated, context, arc=arc)

            name_fixes = [v for v in result.violations if v.constraint_type == "character_name" and v.fix]
            if name_fixes:
                generated = apply_name_fixes(generated, name_fixes)
                click.echo(f"  [FIX] 修正 {len(name_fixes)} 个人名")

            for v in result.violations:
                if v.constraint_type in ("style", "length"):
                    click.echo(f"  [WARN] {v.detail}")

            struct_errors = [v for v in result.violations if v.constraint_type == "structure" and v.severity == "error"]
            if struct_errors:
                click.echo(f"  [RETRY] 结构: {struct_errors[0].detail}")
                try:
                    retry_gen = generate_chapter(write_prompt)
                    retry_result = run_validation(retry_gen, context, arc=arc)
                    if not [v for v in retry_result.violations if v.constraint_type == "structure" and v.severity == "error"]:
                        generated = retry_gen
                        click.echo(f"  [OK] 重试后结构通过")
                    else:
                        click.echo(f"  [WARN] 重试仍有结构问题，保留第一次生成")
                except Exception:
                    click.echo(f"  [WARN] 重试失败，保留第一次生成")

            output_path = project_path(project, "output", f"ch{chapter}_generated.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"第{chapter}章（LLM续写版）\n\n{generated}")
            click.echo(f"  续写完成: {output_path} ({len(generated)} 字)")
        except Exception as e:
            click.echo(f"  [WARN] 续写失败: {e}")

    click.echo(f"\n{'=' * 50}")
    click.echo("闭环完成。")
    click.echo(f"{'=' * 50}")

    kg.close()


# ========== 悬念线审计 ==========

@cli.command("audit-threads")
@click.option("--auto", is_flag=True, help="自动调用LLM检测隐含解决")
@click.pass_context
def audit_threads(ctx, auto):
    """审计悬念线状态，检测隐含解决的线索"""
    project = ctx.obj["project"]
    kg = get_kg(project)

    threads = kg.get_all_threads()
    if not threads:
        click.echo("项目中无悬念线。")
        kg.close()
        return

    click.echo(f"\n--- 悬念线审计（项目: {project}）---")
    click.echo(f"总计: {len(threads)} 条\n")

    # 按状态分组
    by_status = {}
    for t in threads:
        st = t.get("status", "unknown")
        by_status.setdefault(st, []).append(t)

    for status, group in sorted(by_status.items()):
        click.echo(f"【{status}】{len(group)} 条")
        for t in group:
            imp = t.get("importance", "?")
            ch = t.get("planted_chapter", "?")
            tid = t.get("id", "?")
            content = t.get("content", "")[:80]
            click.echo(f"  {tid} [{imp}] ch{ch}: {content}")
        click.echo("")

    # 统计
    unresolved = by_status.get("planted", []) + by_status.get("advanced", []) + \
                 by_status.get("partially_resolved", [])
    click.echo(f"未解决: {len(unresolved)} / {len(threads)}")

    if auto and unresolved:
        click.echo(f"\n正在调用LLM检测隐含解决...")
        # 读取所有章节文本
        output_dir = project_path(project, "output")
        all_text = ""
        for fname in sorted(os.listdir(output_dir)) if os.path.isdir(output_dir) else []:
            if fname.startswith("ch") and fname.endswith("_generated.txt"):
                with open(os.path.join(output_dir, fname), "r", encoding="utf-8") as f:
                    all_text += f.read() + "\n\n"

        if not all_text:
            click.echo("  未找到章节文本，跳过隐含解决检测。")
            kg.close()
            return

        # 构建检测prompt
        thread_list = "\n".join(
            f"  - {t['id']}: {t.get('content', '')} [{t.get('status', '')}]"
            for t in unresolved
        )
        audit_prompt = f"""检查以下未解决悬念线是否在全文中已被隐含解决（读者读完后已知道答案，即使文中未直接提及该悬念线）。

## 未解决悬念线
{thread_list}

## 全文摘要
{all_text[:15000]}

## 返回格式
返回JSON：
{{
  "resolved": [
    {{"thread_id": "ST01_01", "evidence": "哪段文字隐含回答了这个问题", "reasoning": "为什么算已解决"}}
  ]
}}

请返回纯JSON。"""

        try:
            from llm import call_llm
            audit_result = call_llm(audit_prompt, json_mode=True)
            # json_mode=True 已返回解析后的dict，无需再正则/JSON解析
            if isinstance(audit_result, dict):
                resolved = audit_result.get("resolved", [])
                if resolved:
                    click.echo(f"\n检测到 {len(resolved)} 条隐含解决：")
                    for r in resolved:
                        tid = r.get("thread_id", "?")
                        click.echo(f"  {tid}: {r.get('reasoning', '')[:80]}")
                        click.echo(f"    证据: {r.get('evidence', '')[:80]}")

                    do_update = auto and True  # --auto模式下自动更新
                    if not auto:
                        do_update = click.confirm("\n  是否更新这些悬念线状态为resolved？")
                    if do_update:
                        for r in resolved:
                            tid = r.get("thread_id", "")
                            for t in threads:
                                if t.get("id") == tid:
                                    kg.update_suspense_thread(tid, status="resolved")
                                    click.echo(f"    [OK] {tid} → resolved")
                                    break
                else:
                    click.echo("  未检测到隐含解决。")
            else:
                click.echo("  [WARN] LLM返回格式异常，跳过。")
        except Exception as e:
            click.echo(f"  [WARN] 审计失败: {e}")

    kg.close()


if __name__ == "__main__":
    cli()
