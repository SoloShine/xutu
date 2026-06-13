#!/usr/bin/env python3
"""
trace → 视觉小说投影器（POC）

读 Workflow 的 .output（trace 已落盘 = 世界已冻结），
把 trace 投影成两种渲染端：
  1. HTML 单文件视觉小说（立即可看，零安装）—— isActive=false 投影验证
  2. Ren'Py .rpy 脚本（目标渲染端，证明可接入）

验证 thesis：世界冻结后，渲染端只是投影器（isActive=false），无新 LLM 调用、无新误差。
这就是并行渲染 / 误差不累积的工程基础。
"""
import json
import argparse
import html
import sys
from pathlib import Path

# Windows GBK 控制台兼容
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# 投影规则：fabula(trace) → sjuzhet(渲染端)
# ============================================================

LAYER_ORDER = {'L3': 0, 'L2': 1, 'L1': 2, 'cross_cut': 3}
LAYER_COLOR = {
    'L3': '#d4881f',       # 命运=琥珀
    'L2': '#5a9fe8',       # 集体=蓝
    'L1': '#6cc06c',       # 角色=绿
    'cross_cut': '#d8504a', # 裁决=红
}
LAYER_LABEL = {
    'L3': '世界意志 · 命运层',
    'L2': '集体层',
    'L1': '角色层',
    'cross_cut': '规律执行者 · 横切',
}
RENDER_ROLE = {
    'world_will': 'narrator',
    'collective': 'collective',
    'character': 'character',
    'law_enforcer': 'judge',
}


def project(traces):
    """trace 流 → RenderEvent 列表。

    tick 内排序：L3 → L2 → L1 → cross_cut
    （命运先显形 → 集体响应 → 角色行动 → 规则裁决——叙事节奏）
    """
    events = []
    for t in traces:
        speaker = t.get('collective_name') or t.get('agent_id', '?')
        events.append({
            'tick': t.get('tick', 0),
            'layer': t.get('layer', 'L1'),
            'agent_type': t.get('agent_type', 'character'),
            'speaker': speaker,
            'action': t.get('action', '(无行动)'),
            'conflict_with': t.get('conflict_with', []) or [],
            'influence_direction': t.get('influence_direction', ''),
            'render_role': RENDER_ROLE.get(t.get('agent_type'), 'character'),
        })
    events.sort(key=lambda e: (e['tick'], LAYER_ORDER.get(e['layer'], 9), e['speaker']))
    return events


# ============================================================
# HTML 渲染端（自包含单文件视觉小说）
# ============================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background:#0a0a0f; color:#e8e8e8;
    font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
    height:100vh; overflow:hidden;
    display:flex; flex-direction:column;
  }}
  .tabs {{ display:flex; background:#14141c; border-bottom:1px solid #2a2a3a; padding:8px; gap:4px; }}
  .tab {{ padding:8px 20px; cursor:pointer; border-radius:4px; font-size:14px; color:#888; }}
  .tab.active {{ background:#2a2a4a; color:#e8e8e8; }}
  .meta {{ padding:6px 16px; font-size:12px; color:#666; background:#0f0f17; }}
  .stage {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end; padding:40px; cursor:pointer; }}
  .speaker {{ font-size:18px; font-weight:bold; margin-bottom:12px; }}
  .speaker .role {{ font-size:11px; color:#555; margin-left:10px; font-weight:normal; }}
  .dialogue {{ font-size:17px; line-height:1.9; max-height:55vh; overflow-y:auto; padding-right:16px; }}
  .dialogue::-webkit-scrollbar {{ width:4px; }}
  .dialogue::-webkit-scrollbar-thumb {{ background:#333; }}
  .conflicts {{ margin-top:18px; border-left:3px solid #d8504a; padding:8px 0 8px 14px; }}
  .conflicts .label {{ color:#d8504a; font-size:12px; margin-bottom:6px; }}
  .conflicts .c {{ font-size:13px; color:#b08080; line-height:1.7; margin-bottom:4px; }}
  .footer {{ display:flex; justify-content:space-between; align-items:center; padding:10px 24px; background:#0f0f17; border-top:1px solid #2a2a3a; font-size:12px; color:#555; }}
  .progress {{ flex:1; margin:0 20px; height:3px; background:#1f1f2e; border-radius:2px; overflow:hidden; }}
  .progress .bar {{ height:100%; background:#5a9fe8; transition:width .3s; }}
  .hint {{ color:#888; animation:blink 1.4s infinite; }}
  @keyframes blink {{ 50% {{ opacity:0.3; }} }}
</style>
</head>
<body>
  <div class="tabs">
    <div class="tab active" data-mode="hetero">异质配置（1 世界意志 + 3 集体嵌套 + 8 角色 + 规律执行者）</div>
    <div class="tab" data-mode="homo">同质配置（13 赋能式角色）</div>
  </div>
  <div class="meta">{meta}</div>
  <div class="stage" id="stage">
    <div class="speaker" id="speaker"></div>
    <div class="dialogue" id="dialogue"></div>
    <div class="conflicts" id="conflicts" style="display:none;"></div>
  </div>
  <div class="footer">
    <span id="tickLabel">tick -</span>
    <div class="progress"><div class="bar" id="bar"></div></div>
    <span class="hint">空格 / 点击 → 下一条</span>
  </div>
<script>
const DATA = {data_json};
let mode = 'hetero';
let idx = 0;
const stage = document.getElementById('stage');
const spk = document.getElementById('speaker');
const dlg = document.getElementById('dialogue');
const cfl = document.getElementById('conflicts');
const bar = document.getElementById('bar');
const tickLabel = document.getElementById('tickLabel');

function render() {{
  const evts = DATA[mode];
  if (idx >= evts.length) {{
    dlg.innerHTML = '<i>（演化结束。世界已冻结。可切换另一配置对比。）</i>';
    spk.innerHTML = '';
    cfl.style.display='none';
    return;
  }}
  const e = evts[idx];
  const color = DATA.layer_colors[e.layer];
  spk.innerHTML = `<span style="color:${{color}}">${{e.speaker}}</span><span class="role">[L=${{e.layer}} · ${{e.render_role}}${{e.influence_direction?' · '+e.influence_direction:''}}]</span>`;
  dlg.textContent = e.action;
  if (e.conflict_with && e.conflict_with.length) {{
    cfl.style.display='block';
    cfl.innerHTML = '<div class="label">⚡ 触发矛盾</div>' + e.conflict_with.map(c=>`<div class="c">${{c}}</div>`).join('');
  }} else {{
    cfl.style.display='none';
  }}
  tickLabel.textContent = `tick ${{e.tick+1}} / ${{DATA.n_ticks}}  ·  ${{idx+1}}/${{evts.length}}`;
  bar.style.width = ((idx+1)/evts.length*100)+'%';
  dlg.scrollTop = 0;
}}
function next() {{ idx++; render(); }}
stage.addEventListener('click', next);
document.addEventListener('keydown', e => {{
  if (e.code==='Space' || e.code==='ArrowRight') {{ e.preventDefault(); next(); }}
  if (e.code==='ArrowLeft') {{ e.preventDefault(); idx=Math.max(0,idx-1); render(); }}
}});
document.querySelectorAll('.tab').forEach(t => {{
  t.onclick = (ev) => {{
    ev.stopPropagation();
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    mode = t.dataset.mode;
    idx = 0;
    render();
  }};
}});
render();
</script>
</body>
</html>
"""


def to_html(hetero_events, homo_events, scene_meta, out_path):
    data = {
        'hetero': hetero_events,
        'homo': homo_events,
        'layer_colors': LAYER_COLOR,
        'n_ticks': scene_meta.get('n_ticks', 10),
    }
    title = f"世界渲染 · {scene_meta.get('scene','?')}"
    meta = (f"场景: {scene_meta.get('scene','?')}  ·  "
            f"规模: {scene_meta.get('scale','?')}  ·  "
            f"异质 {len(hetero_events)} trace / 同质 {len(homo_events)} trace  ·  "
            f"投影器 isActive=false（无新 LLM 调用）")
    html_text = HTML_TEMPLATE.format(
        title=html.escape(title),
        meta=html.escape(meta),
        data_json=json.dumps(data, ensure_ascii=False),
    )
    Path(out_path).write_text(html_text, encoding='utf-8')
    return len(html_text)


# ============================================================
# Ren'Py 渲染端（目标投影器）
# ============================================================

def to_renpy(events, scene_meta, label_name, out_path):
    """生成 Ren'Py 脚本。

    每个 trace → 1 段对话/旁白。action 文本截断到 220 字（Ren'Py 单行过难看）。
    """
    # 收集所有 speaker（去重），生成 Character define
    speakers = {}
    for e in events:
        if e['speaker'] not in speakers:
            color = LAYER_COLOR.get(e['layer'], '#cccccc')
            var = f"c{len(speakers)}"
            speakers[e['speaker']] = {'var': var, 'color': color}

    lines = []
    lines.append(f"# {'='*60}")
    lines.append(f"# {scene_meta.get('scene','')} — Ren'Py 投影")
    lines.append(f"# 自动生成自 trace（世界冻结态）。isActive=false 投影器。")
    lines.append(f"# {'='*60}")
    lines.append("")
    lines.append('# --- Character 定义（按 layer 着色）---')
    for name, info in speakers.items():
        lines.append(f'define {info["var"]} = Character("{name}", color="{info["color"]}")')
    lines.append('define narrator_world = Character(None, what_prefix="{i}", what_suffix="{/i}", what_color="#d4881f")')
    lines.append('define judge = Character("规律执行者", color="#d8504a")')
    lines.append("")
    scene_name = scene_meta.get('scene', '')
    scale_name = scene_meta.get('scale', '')
    lines.append(f'label {label_name}:')
    lines.append('    scene black')
    lines.append(f'    "[b]{scene_name}[/b]"')
    lines.append(f'    "规模: {scale_name}"')
    lines.append('    "（投影自冻结 trace，无新 LLM 调用。点击继续。）"')
    lines.append('')

    current_tick = -1
    for e in events:
        if e['tick'] != current_tick:
            current_tick = e['tick']
            lines.append(f'    "—— tick {current_tick+1} ——"')
        var = speakers[e['speaker']]['var']
        action = e['action']
        if len(action) > 220:
            action = action[:217] + '...'
        # 转义 Ren'Py 特殊字符
        action = action.replace('"', '\\"').replace('[', '[[').replace('{', '{{')
        if e['render_role'] == 'narrator':
            lines.append(f'    narrator_world "{action}"')
        elif e['render_role'] == 'judge':
            lines.append(f'    judge "{action}"')
        else:
            lines.append(f'    {var} "{action}"')
        if e['conflict_with']:
            first = e['conflict_with'][0]
            first = first.replace('"', '\\"')[:100]
            lines.append(f'    "    {{color=#d8504a}}⚡ {first}{{/color}}"')

    lines.append('')
    lines.append('    "（演化结束。世界已冻结。）"')
    lines.append('    return')

    Path(out_path).write_text('\n'.join(lines), encoding='utf-8')
    return len(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    ap = argparse.ArgumentParser(description='trace → 视觉小说投影')
    ap.add_argument('--input', default=r'C:\Users\Administrator~1\AppData\Local\Temp\claude\D--novel-test\9692d31b-6302-4415-8f13-99df06a36bd0\tasks\wcngxa9px.output',
                    help='Workflow .output 路径')
    ap.add_argument('--outdir', default=None, help='输出目录（默认脚本同目录）')
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else Path(__file__).parent
    outdir.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    result = data.get('result', data)
    scene_meta = {
        'scene': result.get('scene', '?'),
        'scale': result.get('scale', '?'),
        'n_ticks': result.get('n_ticks', 10),
        'hetero_config': result.get('hetero_config', ''),
        'homo_config': result.get('homo_config', ''),
    }
    hetero = project(result.get('hetero_traces', []))
    homo = project(result.get('homo_traces', []))

    print(f"场景: {scene_meta['scene']}")
    print(f"异质 trace: {len(hetero)}  /  同质 trace: {len(homo)}")
    print(f"layer 分布（异质）: ", end='')
    from collections import Counter
    print(dict(Counter(e['layer'] for e in hetero)))

    # 输出 event log（中间产物，给后续写端召回用）
    log_path = outdir / 'event_log.json'
    log_path.write_text(json.dumps({
        'scene_meta': scene_meta,
        'hetero_events': hetero,
        'homo_events': homo,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n[OK] event log: {log_path}")

    # 输出 HTML
    html_path = outdir / 'seal_crisis_visual_novel.html'
    sz = to_html(hetero, homo, scene_meta, html_path)
    print(f"[OK] HTML 视觉小说: {html_path}  ({sz:,} chars)")

    # 输出 Ren'Py（异质 + 同质各一份）
    for name, evts in [('hetero', hetero), ('homo', homo)]:
        rpy_path = outdir / f'seal_crisis_{name}.rpy'
        n = to_renpy(evts, scene_meta, f'{name}_start', rpy_path)
        print(f"[OK] Ren'Py ({name}): {rpy_path}  ({n} lines)")

    print(f"\n打开 HTML 看效果（双击即可）：\n  {html_path}")


if __name__ == '__main__':
    main()
