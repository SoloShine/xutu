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


def load_telemetry(project: str) -> dict:
    """加载项目的所有遥测 JSON。"""
    here = os.path.dirname(os.path.abspath(__file__))
    mvp_dir = os.path.normpath(os.path.join(here, '..', 'novel_kg_mvp'))
    tel_dir = os.path.join(mvp_dir, 'projects', project, 'telemetry')

    if not os.path.isdir(tel_dir):
        print(f"遥测目录不存在: {tel_dir}")
        sys.exit(1)

    data = {"chapters": {}, "summary": None}

    # 按章报告
    for fname in sorted(os.listdir(tel_dir)):
        fpath = os.path.join(tel_dir, fname)
        if fname.startswith("ch") and fname.endswith("_report.json"):
            with open(fpath, "r", encoding="utf-8") as f:
                report = json.load(f)
            ch = report.get("chapter", 0)
            data["chapters"][ch] = report
        elif fname == "session_summary.json":
            with open(fpath, "r", encoding="utf-8") as f:
                data["summary"] = json.load(f)

    return data, tel_dir


def render_dashboard(data: dict, output_path: str):
    """生成 HTML 仪表盘。"""
    chapters = data["chapters"]
    summary = data["summary"]

    # 准备数据
    sorted_ch = sorted(chapters.keys())
    ch_labels = [f"Ch{c}" for c in sorted_ch]

    # 每章总耗时
    ch_totals = []
    for c in sorted_ch:
        r = chapters[c]
        ch_totals.append(r.get("totals", {}).get("duration_ms", 0))

    # 每章工具调用数
    ch_tool_counts = []
    for c in sorted_ch:
        r = chapters[c]
        ch_tool_counts.append(r.get("totals", {}).get("tool_count", 0))

    # 工具耗时分布
    tool_names = []
    tool_means = []
    tool_mins = []
    tool_maxs = []
    tool_counts = []
    if summary and "tool_stats" in summary:
        for name, stats in sorted(summary["tool_stats"].items()):
            tool_names.append(name)
            tool_means.append(stats.get("mean_ms", 0))
            tool_mins.append(stats.get("min_ms", 0))
            tool_maxs.append(stats.get("max_ms", 0))
            tool_counts.append(stats.get("count", 0))

    # 每章各工具耗时（堆叠柱状图）
    all_tools = sorted(set(
        tc["tool"]
        for r in chapters.values()
        for tc in r.get("tool_calls", [])
    ))
    tool_colors = {}
    palette = [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    ]
    for i, t in enumerate(all_tools):
        tool_colors[t] = palette[i % len(palette)]

    stacked_datasets = []
    for t in all_tools:
        vals = []
        for c in sorted_ch:
            r = chapters[c]
            total = sum(
                tc["duration_ms"] for tc in r.get("tool_calls", [])
                if tc["tool"] == t
            )
            vals.append(round(total, 1))
        stacked_datasets.append({
            "label": t,
            "data": vals,
            "backgroundColor": tool_colors[t],
        })

    # 详细表格 HTML
    table_rows = []
    for c in sorted_ch:
        r = chapters[c]
        for tc in r.get("tool_calls", []):
            decision_str = ""
            d = tc.get("decision")
            if d:
                parts = [f"{k}={v}" for k, v in d.items() if v]
                decision_str = ", ".join(parts[:3])
            table_rows.append({
                "chapter": c,
                "tool": tc.get("tool", ""),
                "duration": tc.get("duration_ms", 0),
                "tokens": _fmt_tokens(tc.get("llm_tokens")),
                "decision": decision_str,
                "error": tc.get("error", ""),
            })

    # 概览数字
    total_calls = sum(ch_tool_counts) if ch_tool_counts else 0
    total_duration = sum(ch_totals) if ch_totals else 0
    session_id = (summary or {}).get("session_id", "N/A")

    # 构建 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>遥测仪表盘</title>
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
  h1 {{ font-size: 1.6rem; margin-bottom: 8px; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }}
  .card h2 {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }}
  .metric {{ display: inline-block; margin-right: 32px; margin-bottom: 8px; }}
  .metric .val {{ font-size: 1.8rem; font-weight: 700; color: var(--accent); }}
  .metric .label {{ font-size: 0.75rem; color: var(--muted); display: block; }}
  .chart-wrap {{ position: relative; height: 280px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.82rem;
  }}
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
    font-size: 0.7rem; font-weight: 600;
  }}
  .badge-fast {{ background: rgba(63,185,80,0.15); color: var(--green); }}
  .badge-slow {{ background: rgba(248,81,73,0.15); color: var(--red); }}
  .badge-med {{ background: rgba(210,153,34,0.15); color: var(--orange); }}
</style>
</head>
<body>

<h1>📊 遥测仪表盘</h1>
<p class="subtitle">Session {session_id} · 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<!-- 概览卡片 -->
<div class="card" style="margin-bottom:16px">
  <h2>Session Overview</h2>
  <div class="metric"><span class="val">{len(sorted_ch)}</span><span class="label">章节数</span></div>
  <div class="metric"><span class="val">{total_calls}</span><span class="label">工具调用</span></div>
  <div class="metric"><span class="val">{total_duration:.0f}ms</span><span class="label">MCP总耗时</span></div>
  <div class="metric"><span class="val">{total_duration/max(len(sorted_ch),1):.0f}ms</span><span class="label">平均每章</span></div>
</div>

<!-- 图表网格 -->
<div class="grid">
  <div class="card">
    <h2>Per-Chapter Tool Duration (stacked)</h2>
    <div class="chart-wrap"><canvas id="stackedChart"></canvas></div>
  </div>
  <div class="card">
    <h2>Tool Duration Distribution</h2>
    <div class="chart-wrap"><canvas id="toolDistChart"></canvas></div>
  </div>
  <div class="card">
    <h2>Chapter Total Duration Trend</h2>
    <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
  </div>
  <div class="card">
    <h2>Tool Call Count</h2>
    <div class="chart-wrap"><canvas id="countChart"></canvas></div>
  </div>
</div>

<!-- 工具详情表格 -->
<div class="card">
  <h2>Detailed Tool Calls</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>Chapter</th><th>Tool</th><th>Duration</th><th>Tokens</th><th>Decision</th><th>Error</th></tr>
      </thead>
      <tbody>
        {_render_table_rows(table_rows)}
      </tbody>
    </table>
  </div>
</div>

<script>
// Stacked bar chart
new Chart(document.getElementById('stackedChart'), {{
  type: 'bar',
  data: {{
    labels: {_json(ch_labels)},
    datasets: {_json(stacked_datasets)}
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ stacked: true, grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }} }},
      y: {{ stacked: true, grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }},
           title: {{ display: true, text: 'Duration (ms)', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e6edf3', font: {{ size: 11 }} }} }} }}
  }}
}});

// Tool duration distribution (min/mean/max)
new Chart(document.getElementById('toolDistChart'), {{
  type: 'bar',
  data: {{
    labels: {_json(tool_names)},
    datasets: [
      {{ label: 'Min', data: {_json(tool_mins)}, backgroundColor: '#3fb950' }},
      {{ label: 'Mean', data: {_json(tool_means)}, backgroundColor: '#58a6ff' }},
      {{ label: 'Max', data: {_json(tool_maxs)}, backgroundColor: '#f85149' }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e', maxRotation: 45 }} }},
      y: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }},
           title: {{ display: true, text: 'Duration (ms)', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e6edf3' }} }} }}
  }}
}});

// Chapter trend line
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: {_json(ch_labels)},
    datasets: [{{
      label: 'Total Duration (ms)',
      data: {_json([round(t, 1) for t in ch_totals])},
      borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)',
      fill: true, tension: 0.3, pointRadius: 5, pointBackgroundColor: '#58a6ff'
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }} }},
      y: {{ grid: {{ color: '#30363d' }}, ticks: {{ color: '#8b949e' }},
           title: {{ display: true, text: 'ms', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e6edf3' }} }} }}
  }}
}});

// Tool call count pie
new Chart(document.getElementById('countChart'), {{
  type: 'doughnut',
  data: {{
    labels: {_json(tool_names)},
    datasets: [{{
      data: {_json(tool_counts)},
      backgroundColor: {_json([tool_colors.get(t, '#58a6ff') for t in tool_names])}
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


def _fmt_tokens(tokens) -> str:
    if not tokens:
        return "-"
    p = tokens.get("prompt_tokens", 0)
    c = tokens.get("completion_tokens", 0)
    if p == 0 and c == 0:
        return "-"
    return f"{p}+{c}"


def _render_table_rows(rows: list) -> str:
    parts = []
    for r in rows:
        dur = r["duration"]
        badge = ""
        if dur > 100:
            badge = '<span class="badge badge-slow">SLOW</span>'
        elif dur > 10:
            badge = '<span class="badge badge-med">OK</span>'
        else:
            badge = '<span class="badge badge-fast">FAST</span>'

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

    output = os.path.join(tel_dir, "dashboard.html")
    render_dashboard(data, output)
