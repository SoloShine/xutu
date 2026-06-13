# src/bedrock/style/prompt_gen.py
from dataclasses import dataclass, field
from src.bedrock.repositories.plot_tree import list_beats_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.style.template_repo import get_effective_fingerprint


@dataclass
class PolishPrompt:
    target_distribution: dict
    beat_contracts: list
    requirements: list = field(default_factory=lambda: [
        "对准目标分布（句长/段落长/感官等）", "保持剧情完整", "不压缩字数", "输出完整章节"])

    def to_string(self):
        lines = ["【风格润色任务】"]
        if self.target_distribution:
            lines.append("目标分布（对准此分布）：")
            for dim, dist in self.target_distribution.items():
                if dim.startswith("_"):
                    continue
                items = " | ".join(f"{k} {v:.0%}" for k, v in dist.items()) if isinstance(dist, dict) else str(dist)
                lines.append(f"  {dim}：{items}")
        else:
            lines.append("（无目标分布指纹——按通用网文风格）")
        lines.append("本章 beat 契约：")
        for c in self.beat_contracts:
            lines.append(f"  beat{c.get('beat_id')}: {c.get('purpose', '')}")
        lines.append("要求：" + " / ".join(self.requirements))
        return "\n".join(lines)


@dataclass
class RepairPrompt:
    violations: list
    fix_hints: list
    chapter_context: str = ""
    requirements: list = field(default_factory=lambda: [
        "只修改违规段落，不动其他", "不引入新的违规", "不压缩剧情", "输出完整章节"])

    def to_string(self):
        lines = [f"【定向修复任务】{self.chapter_context}"]
        lines.append("违规清单：")
        for v in self.fix_hints:
            lines.append(f"  - {v}")
        lines.append("要求：" + " / ".join(self.requirements))
        return "\n".join(lines)


def generate_polish_prompt(conn, chapter_id, volume_id):
    """正向润色 prompt：effective fingerprint + 本章 beat 契约。"""
    fp = get_effective_fingerprint(conn, volume_id) or {}
    # 去掉 _scope/_volume_id 元字段（to_string 已过滤，这里也清）
    target = {k: v for k, v in fp.items() if not k.startswith("_")} if fp else {}
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)
    return PolishPrompt(target_distribution=target, beat_contracts=beat_contracts)


def generate_repair_prompt(violations, chapter_context=""):
    """定向修复 prompt：SP2 BeatViolation[]（含 fix_hint）。"""
    fix_hints = [v.fix_hint for v in violations if v.fix_hint]
    return RepairPrompt(violations=violations, fix_hints=fix_hints, chapter_context=chapter_context)
