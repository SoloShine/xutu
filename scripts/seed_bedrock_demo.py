"""SP6-C demo seed：造一个带数据的 bedrock 项目给 Web UI 展示。
用法：python scripts/seed_bedrock_demo.py（覆盖式重建 projects/bedrock_demo）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bedrock.init_project import init_project
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_constant
from src.bedrock.repositories.outline import (
    add_inspiration, advance_inspiration, consume_inspiration,
)

PROJECT = Path(__file__).resolve().parent.parent / "projects" / "bedrock_demo"


def main():
    init_project(PROJECT, work_name="磐石 Demo", force=True)
    conn = get_connection(PROJECT)
    try:
        # work_name 由 init_project 写入（"磐石 Demo"），这里不重复

        # 角色
        hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist",
                              personality="谨慎、执拗")
        ls = create_character(conn, name="林深", pronoun="她", role="supporting",
                              personality="冷静、洞察")
        sy = create_character(conn, name="沈夜", pronoun="他", role="antagonist",
                              personality="阴鸷")

        # 卷1：3 章，韩峥/林深 POV
        v1 = create_volume(conn, 1, "边界", 1, 3, "opening")
        chs = []
        for gnum, title, pov in [(1, "牤晓", hz), (2, "暗涌", ls), (3, "对峙", hz)]:
            cid = create_chapter(conn, volume_id=v1, global_number=gnum, title=title,
                                 status="completed")
            bid = create_beat(conn, chapter_id=cid, sequence=1,
                              purpose=f"{title}的核心场景：人物在边界处做出关键抉择，推动主线",
                              pov_character_id=pov)
            create_paragraph(conn, chapter_id=cid, seq=1,
                             text=f"第{gnum}章「{title}」的开篇段落。韩峥站在封锁线前，城市的电流声在耳膜里嗡鸣。"
                                  "他抬起手，指尖触到那层看不见的膜——温热的，像活物的皮肤。",
                             content_hash=f"h{gnum}1", beat_id=bid, role="narration")
            create_paragraph(conn, chapter_id=cid, seq=2,
                             text=f"林深的声音从背后传来：『不能再等了。』她的语气平静，却带着不容置疑的分量。",
                             content_hash=f"h{gnum}2", beat_id=bid, role="narration")
            chs.append(cid)

        # 卷2：2 章，引入沈夜 POV（多 POV 展示）
        v2 = create_volume(conn, 2, "裂痕", 4, 5, "climax")
        create_chapter(conn, volume_id=v2, global_number=4, title="暗棋", status="completed")
        create_chapter(conn, volume_id=v2, global_number=5, title="摊牌", status="writing")  # 未完成，会被 export 跳过
        cid4 = conn.execute("SELECT id FROM chapter WHERE global_number=4").fetchone()["id"]
        bid4 = create_beat(conn, chapter_id=cid4, sequence=1,
                           purpose="沈夜视角：他在幕后布局，揭示其动机与韩峥命运的交织",
                           pov_character_id=sy)
        create_paragraph(conn, chapter_id=cid4, seq=1,
                         text="沈夜抚过棋盘，黑白子错落如星图。『他们以为自己是棋手，』他低声笑，"
                              "『却不知从一开始，棋局就不是他们能理解的形状。』",
                         content_hash="h41", beat_id=bid4, role="narration")

        # 灵感池：各状态
        i1 = add_inspiration(conn, content="韩峥能听到城市电流声——一种接近通灵的感知，象征他与系统的共振",
                             type="mechanic", source="散步时的想法")
        advance_inspiration(conn, i1, "refined")
        consume_inspiration(conn, i1, target_type="character", target_id=hz)

        i2 = add_inspiration(conn, content="林深的过去：她曾是封锁方案的设计者之一，这成为她的隐痛",
                             type="character", source="人物小传推演")
        advance_inspiration(conn, i2, "refined")
        advance_inspiration(conn, i2, "partial")

        i3 = add_inspiration(conn, content="第二卷用一个多视角结构：韩峥/林深/沈夜三线交替收束到摊牌",
                             type="scene", source="结构构思")

        i4 = add_inspiration(conn, content="沈夜其实是韩峥的镜像——同源不同路",
                             type="twist", source="主题深化")
        advance_inspiration(conn, i4, "refined")

        i5 = add_inspiration(conn, content="加入时间穿越元素", type="mechanic", source="脑洞")
        advance_inspiration(conn, i5, "discarded")  # 弃用

        # review_report_vol1.md（SP5 格式，含 escalate_human）
        report = """# VolumeReview 报告 — 卷 1

## 旗章发现（actionable）
- ch2 [is_actionable=True]: 主语缺失，'她'指代在连续三段中漂移
- ch3 [is_actionable=True]: beat 契约目的未兑现——对峙场景缺少韩峥的抉择落点

## 修正结果（三状态）
- ch1: verified_fixed
- ch2: edited_unverified
- ch3: escalate_human

## Watchdog
（无）

## 跨卷悬链欠债
（无）
"""
        (PROJECT / "review_report_vol1.md").write_text(report, encoding="utf-8")

        conn.commit()
        print(f"[OK] demo 项目就绪：{PROJECT}")
        print(f"   卷：2 | 角色：3 | 章节：5（4 completed + 1 writing）| 灵感：5（含各状态）")
        print(f"   review_report_vol1.md 已生成（ch3 escalate_human）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
