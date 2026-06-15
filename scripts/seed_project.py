"""通用 bedrock 项目种子脚本:从 world_setup JSON 灌入 bedrock.db。

用法:
  python scripts/seed_project.py --project <path> --setup <world_setup.json>

world_setup.json schema(由 novel-creation-wizard 生成):
{
  "title": str, "premise": str,
  "volumes": [{"number":1,"name":"卷名","chapter_start":1,"chapter_end":6,"volume_type":"opening"}],
  "chapters": [{"global_number":1,"volume":1,"title":"章标题","beats":[{"seq":1,"purpose":"...","pov":"角色名"}]}],
  "characters": [{"name":"..","pronoun":"他/她","role":"protagonist|supporting|antagonist","personality":".."}],
  "locations": [{"name":"..","loc_type":"..","description":".."}],
  "themes": [{"name":"..","description":"..","evolution":".."}],
  "motifs": [{"name":"..","meaning":"..","evolution":".."}],
  "time_periods": [{"label":"..","chapter_start":1,"chapter_end":6,"description":".."}],
  "master_outline": {"theme_evolution":"..","key_arcs":[..],"key_milestones":[..],"rhythm_curve":".."}
}

不创建 paragraph —— 正文由 bedrock-chapter.js 的 ChapterWriter 产。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import (
    add_constant, add_location, add_theme, add_motif, add_time_period,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--setup", type=Path, required=True)
    args = ap.parse_args()

    setup = json.loads(args.setup.read_text(encoding="utf-8"))
    conn = get_connection(args.project)
    try:
        add_constant(conn, key="premise", value=setup.get("premise", ""),
                     source_note="seed_project")

        # 角色(先建,beat 的 pov 按名查 id)
        char_id = {}
        for c in setup.get("characters", []):
            cid = create_character(conn, name=c["name"], pronoun=c.get("pronoun", "他"),
                                   role=c.get("role", "supporting"),
                                   personality=c.get("personality", ""))
            char_id[c["name"]] = cid

        # 卷
        vol_id = {}
        for v in setup.get("volumes", []):
            vid = create_volume(conn, v["number"], v["name"], v["chapter_start"],
                                v["chapter_end"], v.get("volume_type", "opening"))
            vol_id[v["number"]] = vid

        # 章 + beat(状态 planned,未写)
        for ch in setup.get("chapters", []):
            cid = create_chapter(conn, volume_id=vol_id[ch["volume"]],
                                 global_number=ch["global_number"],
                                 title=ch["title"], status="planned")
            for b in ch.get("beats", []):
                pov = char_id.get(b.get("pov"))
                create_beat(conn, chapter_id=cid, sequence=b["seq"],
                            purpose=b["purpose"], pov_character_id=pov)

        # worldbook
        for loc in setup.get("locations", []):
            add_location(conn, name=loc["name"], loc_type=loc.get("loc_type", ""),
                         description=loc.get("description", ""))
        for t in setup.get("themes", []):
            add_theme(conn, name=t["name"], description=t.get("description", ""),
                      evolution=t.get("evolution", ""))
        for m in setup.get("motifs", []):
            add_motif(conn, name=m["name"], meaning=m.get("meaning", ""),
                      evolution=m.get("evolution", ""))
        for tp in setup.get("time_periods", []):
            add_time_period(conn, label=tp["label"], chapter_start=tp["chapter_start"],
                            chapter_end=tp["chapter_end"], description=tp.get("description", ""))

        # master_outline
        mo = setup.get("master_outline")
        if mo:
            conn.execute(
                "INSERT OR REPLACE INTO master_outline(id,theme_evolution,key_arcs,key_milestones,rhythm_curve) "
                "VALUES(1,?,?,?,?)",
                (mo.get("theme_evolution", ""),
                 json.dumps(mo.get("key_arcs", []), ensure_ascii=False),
                 json.dumps(mo.get("key_milestones", []), ensure_ascii=False),
                 mo.get("rhythm_curve", "")))

        conn.commit()
        print(f"seeded {args.project}: "
              f"{len(char_id)} chars, {len(vol_id)} vols, "
              f"{len(setup.get('chapters', []))} chapters")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
