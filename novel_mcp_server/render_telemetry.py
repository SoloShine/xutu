"""
V25 遥测可视化 — 从 JSON 生成自包含 HTML 仪表盘。
用法: python render_telemetry.py <project>
输出: projects/<project>/telemetry/dashboard.html
"""

import json
import os
import sys
import html as _html
from datetime import datetime


# ============================================================
# 中英文字典
# ============================================================
I18N = {
    "zh": {
        "title": "📊 遥测仪表盘",
        "session": "会话概览",
        "chapters": "章节数",
        "tool_calls": "工具调用",
        "mcp_total": "MCP总耗时",
        "mcp_avg": "平均每章(MCP)",
        "wall_total": "总墙钟时间",
        "wall_avg": "平均每章(含LLM)",
        "stacked_title": "章节工具负荷结构",
        "dist_title": "最慢章节排行",
        "trend_title": "章节耗时趋势",
        "count_title": "章节负荷桶",
        "detail_title": "工具调用明细",
        "chapter_detail_title": "章节明细",
        "tool_detail_title": "工具调用明细",
        "th_chapter": "章节",
        "th_tool": "工具",
        "th_duration": "耗时",
        "th_tokens": "Token",
        "th_decision": "决策",
        "th_error": "错误",
        "th_purpose": "目的",
        "th_key_events": "关键事件",
        "th_structure": "结构",
        "th_wall": "墙钟",
        "th_mcp": "MCP",
        "th_tools2": "工具数",
        "th_avg_tool": "均值",
        "th_slowest": "最慢工具",
        "th_threads": "线索",
        "th_source": "来源",
        "badge_slow": "慢",
        "badge_med": "中",
        "badge_fast": "快",
        "error_chapters": "有错误章节",
        "error_total": "错误总数",
        "mcp_ms": "MCP工具耗时 (ms)",
        "wall_sec": "墙钟时间（含LLM，秒）",
        "y_mcp": "MCP耗时 (ms)",
        "y_wall": "墙钟时间 (秒)",
        "dist_min": "最小",
        "dist_mean": "平均",
        "dist_max": "最大",
        "y_duration": "耗时 (ms)",
        "generated": "生成于",
        "btn_zh": "中文",
        "btn_en": "EN",
    },
    "en": {
        "title": "📊 Telemetry Dashboard",
        "session": "Session Overview",
        "chapters": "Chapters",
        "tool_calls": "Tool Calls",
        "mcp_total": "MCP Total",
        "mcp_avg": "Avg/Chapter (MCP)",
        "wall_total": "Wall Clock Total",
        "wall_avg": "Avg/Chapter (w/ LLM)",
        "stacked_title": "Chapter Tool Load",
        "dist_title": "Slowest Chapters",
        "trend_title": "Chapter Duration Trend",
        "count_title": "Chapter Load Buckets",
        "detail_title": "Tool Call Details",
        "chapter_detail_title": "Chapter Details",
        "tool_detail_title": "Tool Call Details",
        "th_chapter": "Chapter",
        "th_tool": "Tool",
        "th_duration": "Duration",
        "th_tokens": "Tokens",
        "th_decision": "Decision",
        "th_error": "Error",
        "th_purpose": "Purpose",
        "th_key_events": "Key Events",
        "th_structure": "Structure",
        "th_wall": "Wall Clock",
        "th_mcp": "MCP",
        "th_tools2": "Tools",
        "th_avg_tool": "Avg",
        "th_slowest": "Slowest Tool",
        "th_threads": "Threads",
        "th_source": "Source",
        "badge_slow": "SLOW",
        "badge_med": "OK",
        "badge_fast": "FAST",
        "error_chapters": "Chapters with Errors",
        "error_total": "Total Errors",
        "mcp_ms": "MCP Tool Duration (ms)",
        "wall_sec": "Wall Clock (w/ LLM, seconds)",
        "y_mcp": "MCP Duration (ms)",
        "y_wall": "Wall Clock (sec)",
        "dist_min": "Min",
        "dist_mean": "Mean",
        "dist_max": "Max",
        "y_duration": "Duration (ms)",
        "generated": "Generated",
        "btn_zh": "中文",
        "btn_en": "EN",
    },
}


def load_telemetry(project: str) -> dict:
    """加载项目的所有遥测 JSON。"""
    here = os.path.dirname(os.path.abspath(__file__))
    mvp_dir = os.path.normpath(os.path.join(here, '..', 'novel_kg_mvp'))
    tel_dir = os.path.join(mvp_dir, 'projects', project, 'telemetry')
    project_dir = os.path.join(mvp_dir, 'projects', project)

    if not os.path.isdir(tel_dir):
        print(f"遥测目录不存在: {tel_dir}")
        sys.exit(1)

    data = {"chapters": {}, "summary": None, "outline": []}
    for fname in sorted(os.listdir(tel_dir)):
        fpath = os.path.join(tel_dir, fname)
        if fname.startswith("ch") and fname.endswith("_report.json"):
            with open(fpath, "r", encoding="utf-8") as f:
                report = json.load(f)
            data["chapters"][report.get("chapter", 0)] = report
        elif fname == "session_summary.json":
            with open(fpath, "r", encoding="utf-8") as f:
                data["summary"] = json.load(f)
    outline_path = os.path.join(project_dir, "outline.json")
    if os.path.exists(outline_path):
        with open(outline_path, "r", encoding="utf-8") as f:
            data["outline"] = json.load(f)
    return data, tel_dir


def render_dashboard(data: dict, output_path: str):
    """生成 HTML 仪表盘。"""
    chapters = data["chapters"]
    summary = data["summary"]
    zh = I18N["zh"]

    sorted_ch = sorted(chapters.keys())
    ch_labels = [f"Ch{c}" for c in sorted_ch]
    outline_map = {
        item.get("chapter"): item
        for item in data.get("outline", [])
        if isinstance(item, dict) and item.get("chapter") is not None
    }

    ch_totals = []
    ch_wall_clock = []
    chapter_rows = []
    bucket_labels = ["短", "中", "长"]
    bucket_counts = [0, 0, 0]
    slow_chapters = []
    error_chapters = 0
    total_errors = 0
    total_wall_clock = 0
    for c in sorted_ch:
        r = chapters[c]
        outline = outline_map.get(c, {})
        tool_calls = r.get("tool_calls", [])
        tool_count = len(tool_calls)
        total_ms = r.get("totals", {}).get("duration_ms", 0)
        wall_ms = r.get("wall_clock_ms", 0)
        error_count = sum(1 for tc in tool_calls if tc.get("error"))
        if error_count:
            error_chapters += 1
        total_errors += error_count
        total_wall_clock += wall_ms
        ch_totals.append(total_ms)
        ch_wall_clock.append(wall_ms)
        slow_chapters.append((c, wall_ms))

        if wall_ms < 120000:
            bucket_counts[0] += 1
        elif wall_ms < 300000:
            bucket_counts[1] += 1
        else:
            bucket_counts[2] += 1

        slowest_tool = "-"
        slowest_ms = 0
        if tool_calls:
            slowest = max(tool_calls, key=lambda tc: tc.get("duration_ms", 0))
            slowest_tool = slowest.get("tool", "-")
            slowest_ms = slowest.get("duration_ms", 0)

        chapter_rows.append({
            "chapter": c,
            "purpose": outline.get("purpose", ""),
            "key_events": outline.get("key_events", ""),
            "structure": outline.get("structure_hint", ""),
            "wall_clock_ms": wall_ms,
            "mcp_ms": total_ms,
            "tool_count": tool_count,
            "avg_tool_ms": total_ms / max(tool_count, 1),
            "error_count": error_count,
            "slowest_tool": slowest_tool,
            "slowest_ms": slowest_ms,
            "threads": _compact_threads(outline),
            "source": (r.get("wall_clock_source") or {}).get("method", "auto"),
        })

    all_tools = sorted(set(
        tc["tool"] for r in chapters.values() for tc in r.get("tool_calls", [])
    ))
    palette = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
               "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
    tool_colors = {t: palette[i % len(palette)] for i, t in enumerate(all_tools)}

    stacked_datasets = []
    for t in all_tools:
        vals = []
        for c in sorted_ch:
            r = chapters[c]
            total = sum(tc["duration_ms"] for tc in r.get("tool_calls", []) if tc["tool"] == t)
            vals.append(round(total, 1))
        stacked_datasets.append({"label": t, "data": vals, "backgroundColor": tool_colors[t]})

    tool_rows = []
    for c in sorted_ch:
        r = chapters[c]
        for tc in r.get("tool_calls", []):
            decision_str = ""
            d = tc.get("decision")
            if d:
                parts = [f"{k}={v}" for k, v in d.items() if v]
                decision_str = ", ".join(parts[:3])
            tool_rows.append({
                "chapter": c, "tool": tc.get("tool", ""),
                "duration": tc.get("duration_ms", 0),
                "tokens": _fmt_tokens(tc.get("llm_tokens")),
                "decision": decision_str, "error": tc.get("error", ""),
            })

    total_calls = sum(r.get("totals", {}).get("tool_count", 0) for r in chapters.values())
    total_duration = sum(ch_totals) if ch_totals else 0
    avg_wall_clock = total_wall_clock / max(len(sorted_ch), 1)
    slow_chapters = sorted(slow_chapters, key=lambda item: item[1], reverse=True)[:10]
    slow_chapter_labels = [f"Ch{c}" for c, _ in slow_chapters]
    slow_chapter_values = [round(v / 1000, 1) for _, v in slow_chapters]
    session_id = (summary or {}).get("session_id", "N/A")

    # 墙钟概览
    wc_html = _wall_clock_metrics(sorted_ch, ch_wall_clock)

    # 表格行
    chapter_table_html = _render_chapter_rows(chapter_rows)
    tool_table_html = _render_tool_rows(tool_rows)

    # I18N JSON（供前端JS切换使用）
    i18n_json = json.dumps(I18N, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{zh['title']}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --fg: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --red: #f85149; --green: #3fb950; --orange: #d29922;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 24px; max-width: 1400px; margin: 0 auto;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
  h1 {{ font-size: 1.6rem; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-top: 4px; }}
  .lang-switch {{
    display: flex; gap: 0; border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
  }}
  .lang-btn {{
    padding: 6px 16px; background: var(--card); color: var(--muted);
    border: none; cursor: pointer; font-size: 0.82rem; font-weight: 600;
    transition: all 0.2s;
  }}
  .lang-btn.active {{ background: var(--accent); color: #fff; }}
  .lang-btn:hover:not(.active) {{ background: rgba(88,166,255,0.15); color: var(--fg); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }}
  .card h2 {{ font-size: 0.82rem; color: var(--muted); letter-spacing: 0.5px; margin-bottom: 12px; }}
  .metric {{ display: inline-block; margin-right: 32px; margin-bottom: 8px; }}
  .metric .val {{ font-size: 1.8rem; font-weight: 700; color: var(--accent); }}
  .metric .label {{ font-size: 0.75rem; color: var(--muted); display: block; }}
  .chart-wrap {{ position: relative; height: 280px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th {{
    text-align: left; padding: 8px 10px; background: var(--bg);
    color: var(--muted); font-weight: 500; position: sticky; top: 0;
    border-bottom: 1px solid var(--border);
  }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  tr:hover {{ background: rgba(88,166,255,0.06); }}
  .error {{ color: var(--red); }}
  .decision {{ color: var(--orange); font-size: 0.75rem; }}
  .table-wrap {{ max-height: 400px; overflow-y: auto; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.7rem; font-weight: 600; margin-left: 4px;
  }}
  .badge-fast {{ background: rgba(63,185,80,0.15); color: var(--green); }}
  .badge-slow {{ background: rgba(248,81,73,0.15); color: var(--red); }}
  .badge-med {{ background: rgba(210,153,34,0.15); color: var(--orange); }}
  .wc-divider {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1 data-i18n="title">{zh['title']}</h1>
    <p class="subtitle">{zh['generated']} {datetime.now().strftime('%Y-%m-%d %H:%M')} · Session {session_id}</p>
  </div>
  <div class="lang-switch">
    <button class="lang-btn active" onclick="switchLang('zh')" data-i18n="btn_zh">中文</button>
    <button class="lang-btn" onclick="switchLang('en')" data-i18n="btn_en">EN</button>
  </div>
</div>

<!-- 概览 -->
<div class="card" style="margin-bottom:16px">
  <h2 data-i18n="session">{zh['session']}</h2>
  <div class="metric"><span class="val">{len(sorted_ch)}</span><span class="label" data-i18n="chapters">{zh['chapters']}</span></div>
  <div class="metric"><span class="val">{total_calls}</span><span class="label" data-i18n="tool_calls">{zh['tool_calls']}</span></div>
  <div class="metric"><span class="val">{total_duration:.0f}ms</span><span class="label" data-i18n="mcp_total">{zh['mcp_total']}</span></div>
  <div class="metric"><span class="val">{total_duration/max(len(sorted_ch),1):.0f}ms</span><span class="label" data-i18n="mcp_avg">{zh['mcp_avg']}</span></div>
  <div class="metric"><span class="val">{total_errors}</span><span class="label">{zh['error_total']}</span></div>
  <div class="metric"><span class="val">{error_chapters}</span><span class="label">{zh['error_chapters']}</span></div>
  {wc_html}
</div>

<!-- 图表 -->
<div class="grid">
  <div class="card">
    <h2 data-i18n="stacked_title">{zh['stacked_title']}</h2>
    <div class="chart-wrap"><canvas id="stackedChart"></canvas></div>
  </div>
  <div class="card">
    <h2 data-i18n="dist_title">{zh['dist_title']}</h2>
    <div class="chart-wrap"><canvas id="distChart"></canvas></div>
  </div>
  <div class="card">
    <h2 data-i18n="trend_title">{zh['trend_title']}</h2>
    <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
  </div>
  <div class="card">
    <h2 data-i18n="count_title">{zh['count_title']}</h2>
    <div class="chart-wrap"><canvas id="countChart"></canvas></div>
  </div>
</div>

<!-- 章节明细 -->
<div class="card">
  <h2 data-i18n="chapter_detail_title">{zh['chapter_detail_title']}</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th data-i18n="th_chapter">{zh['th_chapter']}</th>
          <th data-i18n="th_purpose">{zh['th_purpose']}</th>
          <th data-i18n="th_key_events">{zh['th_key_events']}</th>
          <th data-i18n="th_structure">{zh['th_structure']}</th>
          <th data-i18n="th_wall">{zh['th_wall']}</th>
          <th data-i18n="th_mcp">{zh['th_mcp']}</th>
          <th data-i18n="th_tools2">{zh['th_tools2']}</th>
          <th data-i18n="th_avg_tool">{zh['th_avg_tool']}</th>
          <th data-i18n="th_slowest">{zh['th_slowest']}</th>
          <th data-i18n="th_error">{zh['th_error']}</th>
          <th data-i18n="th_threads">{zh['th_threads']}</th>
          <th data-i18n="th_source">{zh['th_source']}</th>
        </tr>
      </thead>
      <tbody>{chapter_table_html}</tbody>
    </table>
  </div>
</div>

<!-- 工具明细 -->
<details class="card" style="margin-top:16px">
  <summary style="cursor:pointer; color:var(--muted); font-size:0.9rem; font-weight:600; margin-bottom:12px;" data-i18n="tool_detail_title">{zh['tool_detail_title']}</summary>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th data-i18n="th_chapter">{zh['th_chapter']}</th>
          <th data-i18n="th_tool">{zh['th_tool']}</th>
          <th data-i18n="th_duration">{zh['th_duration']}</th>
          <th data-i18n="th_tokens">{zh['th_tokens']}</th>
          <th data-i18n="th_decision">{zh['th_decision']}</th>
          <th data-i18n="th_error">{zh['th_error']}</th>
        </tr>
      </thead>
      <tbody>{tool_table_html}</tbody>
    </table>
  </div>
</details>

<script>
const I18N = {i18n_json};
let currentLang = 'zh';
const charts = {{}};

// 所有需要翻译的Chart文本
const chartI18n = {{
  stacked: {{
    y_label: {{ zh: '耗时 (ms)', en: 'Duration (ms)' }}
  }},
  dist: {{
    y_label: {{ zh: '墙钟时间 (秒)', en: 'Wall Clock (sec)' }},
    labels: {{ zh: ['最慢章节'], en: ['Slowest Chapters'] }}
  }},
  trend: {{
    y_mcp: {{ zh: 'MCP耗时 (ms)', en: 'MCP Duration (ms)' }},
    y_wall: {{ zh: '墙钟时间 (秒)', en: 'Wall Clock (sec)' }},
    ds_mcp: {{ zh: 'MCP工具耗时 (ms)', en: 'MCP Tool Duration (ms)' }},
    ds_wall: {{ zh: '墙钟时间（含LLM，秒）', en: 'Wall Clock (w/ LLM, sec)' }},
  }},
  count: {{
    labels: {{ zh: ['短篇', '中篇', '长篇'], en: ['Short', 'Medium', 'Long'] }}
  }}
}};

function switchLang(lang) {{
  currentLang = lang;
  const t = I18N[lang];

  // 按钮状态
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.lang-btn[onclick="${{lang}}'"]`)
    ?? document.querySelectorAll('.lang-btn')[lang === 'zh' ? 0 : 1]
    ?.classList.add('active');

  // 翻译所有 data-i18n 元素
  document.querySelectorAll('[data-i18n]').forEach(el => {{
    const key = el.getAttribute('data-i18n');
    if (t[key]) el.textContent = t[key];
  }});

  // 更新图表标签
  updateCharts(lang);
}}

function updateCharts(lang) {{
  const t = I18N[lang];

  // 堆叠柱状图 Y轴
  if (charts.stacked) {{
    charts.stacked.options.scales.y.title.text = chartI18n.stacked.y_label[lang];
    charts.stacked.update();
  }}

  // 分布图
  if (charts.dist) {{
    charts.dist.data.datasets[0].label = chartI18n.dist.labels[lang][0];
    charts.dist.options.scales.x.title.text = chartI18n.dist.y_label[lang];
    charts.dist.update();
  }}

  // 趋势图
  if (charts.trend) {{
    charts.trend.data.datasets[0].label = chartI18n.trend.ds_mcp[lang];
    charts.trend.options.scales.y.title.text = chartI18n.trend.y_mcp[lang];
    if (charts.trend.data.datasets.length > 1) {{
      charts.trend.data.datasets[1].label = chartI18n.trend.ds_wall[lang];
      charts.trend.options.scales.y1.title.text = chartI18n.trend.y_wall[lang];
    }}
    charts.trend.update();
  }}

  if (charts.count) {{
    charts.count.data.labels = chartI18n.count.labels[lang];
    charts.count.update();
  }}

  // 表格徽章
  document.querySelectorAll('.badge-fast').forEach(b => b.textContent = t.badge_fast);
  document.querySelectorAll('.badge-med').forEach(b => b.textContent = t.badge_med);
  document.querySelectorAll('.badge-slow').forEach(b => b.textContent = t.badge_slow);
}}

// ---- 初始化图表 ----

// 每章工具耗时（堆叠柱状图）
charts.stacked = new Chart(document.getElementById('stackedChart'), {{
  type: 'bar',
  data: {{ labels: {_json(ch_labels)}, datasets: {_json(stacked_datasets)} }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ stacked: true, grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }} }},
      y: {{ stacked: true, grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }},
           title: {{ display: true, text: '耗时 (ms)', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e6edf3', font: {{ size: 11 }} }} }} }}
  }}
}});

// 最慢章节排行
charts.dist = new Chart(document.getElementById('distChart'), {{
  type: 'bar',
  data: {{
    labels: {_json(slow_chapter_labels)},
    datasets: [
      {{ label: '{zh['wall_sec']}', data: {_json(slow_chapter_values)}, backgroundColor: '#f28e2b' }},
    ]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }},
           title: {{ display: true, text: '墙钟时间 (秒)', color: '#8b949e' }} }},
      y: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// 耗时趋势（MCP vs 墙钟）
const hasWallClock = {_json(any(v > 0 for v in ch_wall_clock))};
const trendDS = [{{
  label: 'MCP工具耗时 (ms)',
  data: {_json([round(t, 1) for t in ch_totals])},
  borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)',
  fill: true, tension: 0.3, pointRadius: 5, pointBackgroundColor: '#58a6ff',
  yAxisID: 'y'
}}];
if (hasWallClock) {{
  trendDS.push({{
    label: '墙钟时间（含LLM，秒）',
    data: {_json([round(v/1000, 1) for v in ch_wall_clock])},
    borderColor: '#f28e2b', backgroundColor: 'rgba(242,142,43,0.1)',
    fill: false, tension: 0.3, pointRadius: 5, pointBackgroundColor: '#f28e2b',
    borderDash: [5, 3], yAxisID: 'y1'
  }});
}}
const trendScales = {{
  x: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }} }},
  y: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#58a6ff' }},
       title: {{ display: true, text: 'MCP耗时 (ms)', color: '#58a6ff' }} }}
}};
if (hasWallClock) {{
  trendScales['y1'] = {{
    position: 'right', grid: {{ drawOnChartArea: false }},
    ticks: {{ color: '#f28e2b' }},
    title: {{ display: true, text: '墙钟时间 (秒)', color: '#f28e2b' }}
  }};
}}
charts.trend = new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{ labels: {_json(ch_labels)}, datasets: trendDS }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: trendScales,
    plugins: {{ legend: {{ labels: {{ color: '#e6edf3' }} }} }}
  }}
}});

// 章节负荷桶
charts.count = new Chart(document.getElementById('countChart'), {{
  type: 'doughnut',
  data: {{
    labels: {_json(bucket_labels)},
    datasets: [{{
      data: {_json(bucket_counts)},
      backgroundColor: ['#3fb950', '#58a6ff', '#f28e2b']
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'right', labels: {{ color: '#e6edf3', font: {{ size: 11 }} }} }} }}
  }}
}});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"仪表盘已生成: {output_path}")


# ============================================================
# 辅助函数
# ============================================================

def _wall_clock_metrics(sorted_ch, ch_wall_clock) -> str:
    has_data = any(v > 0 for v in ch_wall_clock)
    if not has_data:
        return ""
    total_wc = sum(v for v in ch_wall_clock)
    avg_wc = total_wc / max(len(sorted_ch), 1)
    return (
        f'<div class="wc-divider">'
        f'<div class="metric"><span class="val">{_fmt_duration(total_wc)}</span>'
        f'<span class="label" data-i18n="wall_total">总墙钟时间</span></div>'
        f'<div class="metric"><span class="val">{_fmt_duration(avg_wc)}</span>'
        f'<span class="label" data-i18n="wall_avg">平均每章(含LLM)</span></div>'
        f'</div>'
    )


def _fmt_duration(ms) -> str:
    if ms <= 0:
        return "N/A"
    s = ms / 1000
    if s < 60:
        return f"{s:.1f}s"
    m = s / 60
    if m < 60:
        return f"{m:.1f}min"
    return f"{m/60:.1f}h"


def _fmt_tokens(tokens) -> str:
    if not tokens:
        return "-"
    p = tokens.get("prompt_tokens", 0)
    c = tokens.get("completion_tokens", 0)
    return f"{p}+{c}" if (p or c) else "-"


def _short_html(text: str, limit: int = 48) -> str:
    raw = text or "-"
    display = raw if len(raw) <= limit else raw[: max(limit - 1, 1)] + "…"
    return f'<span title="{_html.escape(raw)}">{_html.escape(display)}</span>'


def _compact_threads(outline: dict) -> str:
    if not outline:
        return "-"
    parts = []
    plant = (outline.get("threads_to_plant") or "").strip()
    resolve = (outline.get("threads_to_resolve") or "").strip()
    if plant and plant != "无":
        parts.append(f"植入:{plant}")
    if resolve and resolve != "无":
        parts.append(f"回收:{resolve}")
    return " / ".join(parts) if parts else "-"


def _render_chapter_rows(rows: list) -> str:
    parts = []
    for r in rows:
        wall = _fmt_duration(r["wall_clock_ms"])
        mcp = f'{r["mcp_ms"]:.1f}ms'
        avg_tool = f'{r["avg_tool_ms"]:.1f}ms'
        slowest = f'{_html.escape(r["slowest_tool"])} ({r["slowest_ms"]:.1f}ms)' if r["slowest_tool"] != "-" else "-"
        err_cls = ' class="error"' if r["error_count"] else ""
        parts.append(
            f'<tr>'
            f'<td>Ch{r["chapter"]}</td>'
            f'<td>{_short_html(r["purpose"], 40)}</td>'
            f'<td>{_short_html(r["key_events"], 56)}</td>'
            f'<td>{_html.escape(r["structure"] or "-")}</td>'
            f'<td>{wall}</td>'
            f'<td>{mcp}</td>'
            f'<td>{r["tool_count"]}</td>'
            f'<td>{avg_tool}</td>'
            f'<td>{slowest}</td>'
            f'<td{err_cls}>{r["error_count"]}</td>'
            f'<td>{_short_html(r["threads"], 60)}</td>'
            f'<td>{_html.escape(r["source"] or "-")}</td>'
            f'</tr>'
        )
    return "\n".join(parts)


def _render_tool_rows(rows: list) -> str:
    parts = []
    for r in rows:
        dur = r["duration"]
        if dur > 100:
            badge = '<span class="badge badge-slow">慢</span>'
        elif dur > 10:
            badge = '<span class="badge badge-med">中</span>'
        else:
            badge = '<span class="badge badge-fast">快</span>'
        err_cls = ' class="error"' if r["error"] else ""
        parts.append(
            f'<tr>'
            f'<td>Ch{r["chapter"]}</td>'
            f'<td>{_html.escape(r["tool"])}</td>'
            f'<td>{dur:.1f}ms {badge}</td>'
            f'<td>{r["tokens"]}</td>'
            f'<td class="decision">{_html.escape(r["decision"])}</td>'
            f'<td{err_cls}>{_html.escape(r["error"])}</td>'
            f'</tr>'
        )
    return "\n".join(parts)


def _json(obj):
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python render_telemetry.py <project>")
        sys.exit(1)
    project = sys.argv[1]
    data, tel_dir = load_telemetry(project)
    if not data["chapters"] and not data["summary"]:
        print(f"项目 '{project}' 无遥测数据")
        sys.exit(1)
    render_dashboard(data, os.path.join(tel_dir, "dashboard.html"))
