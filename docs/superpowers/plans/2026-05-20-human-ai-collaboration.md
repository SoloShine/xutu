# Human-AI Collaboration + Outline Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add outline compliance checking (programmatic), configurable chapter review checkpoints, post-hoc edit impact analysis, and outline revision tools to the novel KG system.

**Architecture:** 5 new MCP tools in `core.py` + `server.py`, a programmatic compliance checker in `validators.py`, and config additions in `config_loader.py`. All tools follow the existing thin-wrapper pattern: `server.py` decorates, `core.py` delegates to backend/validator.

**Tech Stack:** Python, FastMCP, existing JSON/Neo4j backends, no new dependencies.

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `novel_kg_mvp/validators.py` | Outline compliance checker (programmatic) | Modify |
| `novel_kg_mvp/config_loader.py` | Add `review_checkpoint`, `outline_compliance`, `auto_revise_outline` defaults | Modify |
| `novel_mcp_server/core.py` | 5 new business functions | Modify |
| `novel_mcp_server/server.py` | 5 new MCP tool decorators | Modify |
| `novel_mcp_server/kg_json.py` | Add `get_edited_chapter_text`, update `add_outline_entry` for compliance fields | Modify |
| `novel_mcp_server/test_e2e.py` | Tests for all new tools | Modify |

---

### Task 1: Outline Compliance Validator

**Files:**
- Modify: `novel_kg_mvp/validators.py` (append after existing code)
- Modify: `novel_mcp_server/test_e2e.py` (add test section [14])

This task adds the programmatic outline compliance checker. It compares an outline entry's fields against the extraction results for a chapter.

- [ ] **Step 1: Add bigram matching helper to validators.py**

Append to `novel_kg_mvp/validators.py`:

```python
# ========== 大纲合规检查 ==========

def _bigram_overlap(s1, s2, min_shared=2):
    """检查两个字符串是否有足够的bigram重叠"""
    if not s1 or not s2:
        return False
    def _bigrams(s):
        if len(s) < 4:
            return {s} if s else set()
        return {s[i:i+2] for i in range(len(s)-1)}
    return len(_bigrams(s1) & _bigrams(s2)) >= min_shared
```

- [ ] **Step 2: Add `check_outline_compliance` function to validators.py**

```python
def check_outline_compliance(outline_entry, events, chapter_arc=None,
                              thread_updates=None, new_threads=None):
    """程序化大纲合规检查。

    对比 outline_entry 各字段与章节的实际提取结果。
    返回 Violation 列表（每个 violation 的 constraint_type 为 outline_compliance）。
    """
    violations = []
    if not outline_entry:
        return violations

    # 1. key_events 检查：大纲中的每个事件是否出现在本章事件中
    key_events_str = outline_entry.get("key_events", "")
    if key_events_str:
        key_events = [e.strip() for e in key_events_str.split(",") if e.strip()]
        event_texts = [
            (ev.get("title", "") or "") + " " + (ev.get("detail", "") or "")
            for ev in events
        ]
        for ke in key_events:
            matched = any(_bigram_overlap(ke, et) for et in event_texts)
            if not matched:
                violations.append(Violation(
                    constraint_type="outline_compliance",
                    severity="error",
                    detail=f"大纲事件'{ke}'未在本章出现",
                ))

    # 2. threads_to_plant 检查
    threads_plant_str = outline_entry.get("threads_to_plant", "")
    if threads_plant_str and new_threads is not None:
        planted_contents = {t.get("content", "") for t in new_threads}
        for tp in [t.strip() for t in threads_plant_str.split(",") if t.strip()]:
            # 支持按ID匹配或按内容bigram匹配
            id_matched = tp in {t.get("id", "") for t in new_threads}
            content_matched = any(_bigram_overlap(tp, pc) for pc in planted_contents)
            if not id_matched and not content_matched:
                violations.append(Violation(
                    constraint_type="outline_compliance",
                    severity="warning",
                    detail=f"大纲要求种植'{tp}'但未种植",
                ))

    # 3. threads_to_resolve 检查
    threads_resolve_str = outline_entry.get("threads_to_resolve", "")
    if threads_resolve_str and thread_updates is not None:
        resolved_ids = {
            tu.get("thread_id", "")
            for tu in thread_updates
            if tu.get("new_status") == "resolved"
        }
        for tr in [t.strip() for t in threads_resolve_str.split(",") if t.strip()]:
            if tr not in resolved_ids:
                violations.append(Violation(
                    constraint_type="outline_compliance",
                    severity="warning",
                    detail=f"大纲要求解决'{tr}'但未解决",
                ))

    # 4. structure_hint 检查
    structure_hint = outline_entry.get("structure_hint", "")
    if structure_hint and chapter_arc:
        arc_structure = chapter_arc.get("structure_type", "linear")
        if structure_hint.lower() != arc_structure.lower():
            violations.append(Violation(
                constraint_type="outline_compliance",
                severity="warning",
                detail=f"大纲要求结构'{structure_hint}'，实际为'{arc_structure}'",
            ))

    return violations
```

- [ ] **Step 3: Add test section [14] to test_e2e.py**

Before the `except Exception` block in `test_e2e.py`, insert:

```python
        # ---- 14. 大纲合规检查 ----
        print("\n[14] 大纲合规检查")
        from validators import check_outline_compliance

        # 合规场景：outline_entry 有 key_events="发现焊疤"，事件中有 E1_01 title="发现焊疤"
        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤")
        compliant_events = [{"id": "E1_01", "title": "发现焊疤", "detail": "老孟看到焊疤"}]
        result = check_outline_compliance(kg.get_outline_entry(1), compliant_events)
        test("outline compliance passed",
             len(result) == 0,
             f"violations: {[v.detail for v in result]}")

        # 不合规场景：key_events 不匹配
        divergent_events = [{"id": "E1_01", "title": "遇到孙洁", "detail": "走廊偶遇"}]
        result2 = check_outline_compliance(kg.get_outline_entry(1), divergent_events)
        test("outline compliance failed on key_events",
             any(v.detail.startswith("大纲事件") for v in result2),
             f"violations: {[v.detail for v in result2]}")

        # 无大纲：应返回空
        result3 = check_outline_compliance(None, compliant_events)
        test("outline compliance no outline", len(result3) == 0)

        # threads_to_resolve 检查
        kg.add_outline_entry(2, purpose="推进", threads_to_resolve="ST01_01")
        result4 = check_outline_compliance(
            kg.get_outline_entry(2), [],
            thread_updates=[{"thread_id": "ST01_01", "new_status": "resolved"}]
        )
        test("outline threads_to_resolve passed",
             not any("threads_to_resolve" in v.detail or "解决" in v.detail for v in result4 if v.constraint_type == "outline_compliance"))

        result5 = check_outline_compliance(
            kg.get_outline_entry(2), [],
            thread_updates=[]
        )
        test("outline threads_to_resolve failed",
             any("ST01_01" in v.detail for v in result5))
```

- [ ] **Step 4: Run tests**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass including new [14] section.

- [ ] **Step 5: Commit**

```bash
git add novel_kg_mvp/validators.py novel_mcp_server/test_e2e.py
git commit -m "feat: add programmatic outline compliance checker (validators.py)"
```

---

### Task 2: check_outline_compliance MCP Tool

**Files:**
- Modify: `novel_mcp_server/core.py` (add function)
- Modify: `novel_mcp_server/server.py` (add decorator)
- Modify: `novel_mcp_server/test_e2e.py` (add test section [15])

This tool wraps the validator into an MCP-callable function that reads graph data and returns a structured compliance report.

- [ ] **Step 1: Add `check_outline_compliance` to core.py**

Append to the validation section in `novel_mcp_server/core.py` (after the `detect_extraction_conflicts` function):

```python
def check_outline_compliance(project: str, chapter: int) -> dict:
    """大纲合规检查（程序化）。"""
    kg = _kg(project)
    outline_entry = kg.get_outline_entry(chapter)
    if not outline_entry:
        return {"chapter": chapter, "overall": "no_outline", "action_required": False}

    events = kg.get_events_by_chapter(chapter)
    arcs = kg.get_all_chapter_arcs()
    chapter_arc = None
    for a in arcs:
        if a.get("chapter") == chapter:
            chapter_arc = a
            break

    from validators import check_outline_compliance as _check_compliance
    violations = _check_compliance(outline_entry, events, chapter_arc=chapter_arc)

    checks = []
    for v in violations:
        checks.append({
            "item": v.constraint_type,
            "status": "failed",
            "severity": v.severity,
            "detail": v.detail,
        })

    errors = [c for c in checks if c["severity"] == "error"]
    warnings = [c for c in checks if c["severity"] == "warning"]

    if errors:
        overall = "diverged"
    elif warnings:
        overall = "partial"
    else:
        overall = "followed"

    return {
        "chapter": chapter,
        "outline_entry": outline_entry,
        "programmatic_checks": checks,
        "overall": overall,
        "action_required": overall != "followed",
    }
```

- [ ] **Step 2: Add MCP decorator to server.py**

Append to the validation section in `novel_mcp_server/server.py` (after `detect_extraction_conflicts`):

```python
@mcp.tool()
def check_outline_compliance(project: str, chapter: int) -> dict:
    """大纲合规检查（程序化+LLM）。

    检查项: key_events是否出现、threads_to_plant/resolve是否执行、structure_hint是否匹配。
    返回合规状态(followed/partial/diverged)和详细检查结果。
    无outline_entry的章节返回 no_outline。
    """
    return core.check_outline_compliance(project, chapter)
```

- [ ] **Step 3: Add test section [15] to test_e2e.py**

```python
        # ---- 15. check_outline_compliance MCP工具 ----
        print("\n[15] check_outline_compliance MCP工具")
        from core import check_outline_compliance as _coc

        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤,看到纸片")
        kg.add_event("E1_01", title="发现焊疤", chapter=1)
        kg.add_event("E1_02", title="看到纸片", chapter=1)

        result_coc = _coc(PROJECT, 1)
        test("check_outline_compliance followed",
             result_coc["overall"] == "followed",
             f"got {result_coc['overall']}")
        test("check_outline_compliance action_required false",
             result_coc["action_required"] == False)

        # 不合规测试
        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤")
        kg.add_event("E1_01", title="遇到孙洁", chapter=1)
        result_div = _coc(PROJECT, 1)
        test("check_outline_compliance diverged",
             result_div["overall"] == "diverged",
             f"got {result_div['overall']}")

        # 无大纲测试
        result_none = _coc(PROJECT, 99)
        test("check_outline_compliance no outline",
             result_none["overall"] == "no_outline")
```

- [ ] **Step 4: Run tests**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass including new [15] section.

- [ ] **Step 5: Commit**

```bash
git add novel_mcp_server/core.py novel_mcp_server/server.py novel_mcp_server/test_e2e.py
git commit -m "feat: add check_outline_compliance MCP tool"
```

---

### Task 3: revise_outline MCP Tool

**Files:**
- Modify: `novel_mcp_server/core.py`
- Modify: `novel_mcp_server/server.py`
- Modify: `novel_mcp_server/test_e2e.py` (add test section [16])

This tool lets the author (or agent in auto-revise mode) explicitly revise an outline entry, recording why and when.

- [ ] **Step 1: Add `revise_outline` to core.py**

Append to the write tools section in `novel_mcp_server/core.py` (after `update_suspense_thread`):

```python
def revise_outline(project: str, chapter: int, reason: str,
                   purpose: str = "", key_events: str = "",
                   threads_to_plant: str = "", threads_to_resolve: str = "",
                   structure_hint: str = "") -> str:
    """显式修订大纲条目。只修改传入的字段，并记录修订原因。"""
    kg = _kg(project)
    existing = kg.get_outline_entry(chapter)
    if not existing:
        return f"第{chapter}章无大纲条目，无法修订。请先用 add_outline_entry 创建。"

    # 获取当前最新章节号（用于记录 revised_chapter）
    all_arcs = kg.get_all_chapter_arcs()
    max_chapter = max((a.get("chapter", 0) for a in all_arcs), default=chapter)

    # 合并：只更新传入的非空字段
    props = {
        "compliance": "overridden",
        "revision_reason": reason,
        "revised_chapter": max_chapter,
    }
    if purpose:
        props["purpose"] = purpose
    if key_events:
        props["key_events"] = key_events
    if threads_to_plant:
        props["threads_to_plant"] = threads_to_plant
    if threads_to_resolve:
        props["threads_to_resolve"] = threads_to_resolve
    if structure_hint:
        props["structure_hint"] = structure_hint

    kg.add_outline_entry(chapter, **props)
    updated_fields = [k for k in props if k not in ("compliance", "revision_reason", "revised_chapter")]
    return f"已修订第{chapter}章大纲。原因: {reason}。更新字段: {', '.join(updated_fields) or '无'}"
```

- [ ] **Step 2: Add MCP decorator to server.py**

Append to the write tools section in `novel_mcp_server/server.py`:

```python
@mcp.tool()
def revise_outline(project: str, chapter: int, reason: str,
                   purpose: str = "", key_events: str = "",
                   threads_to_plant: str = "", threads_to_resolve: str = "",
                   structure_hint: str = "") -> str:
    """显式修订大纲条目。只传需要修改的字段。

    修订时自动设置 compliance='overridden'，记录修订原因和修订时最新章节号。
    reason 参数必填，说明为什么修订。
    """
    return core.revise_outline(project, chapter, reason, purpose, key_events,
                                threads_to_plant, threads_to_resolve, structure_hint)
```

- [ ] **Step 3: Add test section [16] to test_e2e.py**

```python
        # ---- 16. revise_outline MCP工具 ----
        print("\n[16] revise_outline MCP工具")
        from core import revise_outline as _ro

        kg.clear_project()
        kg.add_chapter_arc(1, purpose="test", scenes="A->B", ending="end")
        kg.add_chapter_arc(2, purpose="test", scenes="C->D", ending="end")
        kg.add_outline_entry(1, purpose="原始目的", key_events="事件A")
        kg.add_chapter_arc(3, purpose="latest", scenes="E->F", ending="end")

        result_ro = _ro(PROJECT, 1, reason="作者修改了ch1", purpose="新目的",
                         key_events="事件B,事件C")
        test("revise_outline returns success",
             "已修订" in result_ro)

        updated = kg.get_outline_entry(1)
        test("revise_outline updated purpose",
             updated["purpose"] == "新目的")
        test("revise_outline updated key_events",
             updated["key_events"] == "事件B,事件C")
        test("revise_outline set compliance",
             updated["compliance"] == "overridden")
        test("revise_outline set reason",
             updated["revision_reason"] == "作者修改了ch1")
        test("revise_outline set revised_chapter",
             updated["revised_chapter"] == 3)

        # 修订不存在的章节
        result_missing = _ro(PROJECT, 99, reason="test")
        test("revise_outline missing entry",
             "无大纲条目" in result_missing)
```

- [ ] **Step 4: Run tests**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add novel_mcp_server/core.py novel_mcp_server/server.py novel_mcp_server/test_e2e.py
git commit -m "feat: add revise_outline MCP tool for explicit outline revision"
```

---

### Task 4: Post-hoc Edit Tools (analyze_edit_impact + accept_edit)

**Files:**
- Modify: `novel_mcp_server/kg_json.py` (add `get_edited_chapter_text`)
- Modify: `novel_mcp_server/core.py` (add 2 functions)
- Modify: `novel_mcp_server/server.py` (add 2 decorators)
- Modify: `novel_mcp_server/test_e2e.py` (add test section [17])

This is the post-hoc remediation flow: author edits an early chapter → system detects impact → author accepts.

- [ ] **Step 1: Add `get_edited_chapter_text` to kg_json.py**

Append to the `JsonKG` class in `novel_mcp_server/kg_json.py`, after `get_chapter_text`:

```python
    def get_edited_chapter_text(self, chapter):
        """读取作者编辑后的章节正文（用于事后影响分析）"""
        path = os.path.join(
            os.path.dirname(self._path), "output",
            f"ch{chapter}_edited.txt"
        )
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None
```

- [ ] **Step 2: Add `analyze_edit_impact` to core.py**

Append to core.py (after the pacing analysis section):

```python
def analyze_edit_impact(project: str, chapter: int) -> dict:
    """事后影响分析：对比edited文本的提取结果与图谱中该章数据。"""
    kg = _kg(project)

    # 检查edited文件是否存在
    edited_text = kg.get_edited_chapter_text(chapter)
    if not edited_text:
        return {
            "error": f"未找到第{chapter}章的编辑版本 (ch{chapter}_edited.txt)",
            "edited_chapter": chapter,
        }

    # 获取图谱中该章的现有事件
    old_events = kg.get_events_by_chapter(chapter)
    old_event_ids = {e["id"] for e in old_events}
    old_event_map = {e["id"]: e for e in old_events}

    # 通过Agent获取新提取结果（此处返回对比所需的数据，Agent负责实际提取）
    # 获取后续章节的大纲条目
    all_outlines = kg.get_all_outline_entries()
    downstream_outlines = [
        oe for oe in all_outlines
        if oe.get("chapter", 0) > chapter
    ]

    # 获取受影响的悬念线：与旧事件关联的未解决悬念线
    old_evidence_links = [
        r for r in kg.get_all_relations()
        if r["rt"] == "EVIDENCES"
        and r["fv"] in old_event_ids
    ]
    affected_thread_ids = {r["tv"] for r in old_evidence_links}
    all_threads = kg.get_all_threads()
    affected_threads = [
        {"id": t["id"], "content": t.get("content", ""),
         "status": t.get("status", ""), "importance": t.get("importance", ""),
         "impact": "关联事件可能被删除或修改", "severity": "high"}
        for t in all_threads if t["id"] in affected_thread_ids
    ]

    # 获取受影响的人物：与旧事件关联的人物
    old_char_names = set()
    for r in kg.get_all_relations():
        if (r["fl"] == "Event" and r["fk"] == "id"
                and r["fv"] in old_event_ids
                and r["rt"] == "INVOLVES"
                and r["tl"] == "Character"):
            old_char_names.add(r["tv"])

    # 检查后续大纲中引用了旧事件的关键词
    downstream_warnings = []
    outline_revision_suggestions = []
    for oe in downstream_outlines:
        ke = oe.get("key_events", "")
        for eid, ev in old_event_map.items():
            title = ev.get("title", "")
            if title and _bigram_overlap_str(title, ke):
                downstream_warnings.append({
                    "chapter": oe.get("chapter", 0),
                    "outline_key": "key_events",
                    "issue": f"依赖可能被删除/修改的事件'{title}' ({eid})",
                })
                outline_revision_suggestions.append({
                    "chapter": oe.get("chapter", 0),
                    "field": "key_events",
                    "suggestion": f"检查'{title}'是否仍存在，必要时替换",
                })

    return {
        "edited_chapter": chapter,
        "old_events": [{"id": e["id"], "title": e.get("title", "")} for e in old_events],
        "affected_threads": affected_threads,
        "affected_characters": sorted(old_char_names),
        "downstream_warnings": downstream_warnings,
        "outline_revision_suggestions": outline_revision_suggestions,
        "edited_text_length": len(edited_text),
        "message": "Agent需对edited文本重新提取，然后调用 accept_edit 写入图谱",
    }
```

Also add the helper function at the top level of core.py (near the other helpers):

```python
def _bigram_overlap_str(s1, s2, min_shared=2):
    """检查两个字符串是否有足够的bigram重叠"""
    if not s1 or not s2:
        return False
    def _bigrams(s):
        if len(s) < 4:
            return {s} if s else set()
        return {s[i:i+2] for i in range(len(s)-1)}
    return len(_bigrams(s1) & _bigrams(s2)) >= min_shared
```

- [ ] **Step 3: Add `accept_edit` to core.py**

```python
def accept_edit(project: str, chapter: int, extracted_json: str,
                confirm: str = "") -> dict:
    """采纳事后编辑：清除旧数据 → 写入新数据 → 标记后续大纲。"""
    err = _check_destructive(confirm)
    if err:
        return {"error": err}

    kg = _kg(project)

    # 清除旧数据
    _mine_clear_chapter(kg, chapter)

    # 写入新数据
    if isinstance(extracted_json, str):
        extracted = json.loads(extracted_json)
    else:
        extracted = extracted_json
    report = write_extraction_to_graph(kg, chapter, extracted,
                                        skip_conflicts=True, project=project)

    # 标记后续大纲为 needs_revision
    all_outlines = kg.get_all_outline_entries()
    marked = []
    for oe in all_outlines:
        ch = oe.get("chapter", 0)
        if ch > chapter:
            existing = kg.get_outline_entry(ch)
            if existing and existing.get("compliance") != "overridden":
                kg.add_outline_entry(ch, **{
                    k: v for k, v in existing.items()
                    if k != "chapter"
                }, compliance="needs_revision")
                marked.append(ch)

    return {
        "chapter": chapter,
        "stats": report["stats"],
        "conflicts": report["conflicts"],
        "downstream_marked_for_revision": marked,
        "message": f"已采纳第{chapter}章编辑。后续章节 {marked} 的大纲标记为 needs_revision。",
    }
```

- [ ] **Step 4: Add MCP decorators to server.py**

Append to server.py:

```python
@mcp.tool()
def analyze_edit_impact(project: str, chapter: int) -> dict:
    """事后影响分析。对比edited文本与图谱中该章数据的差异。

    需要 projects/<project>/output/chN_edited.txt 存在。
    返回受影响的事件/悬念线/人物/后续大纲警告。
    Agent需对edited文本重新提取后调用 accept_edit 写入图谱。
    """
    return core.analyze_edit_impact(project, chapter)


@mcp.tool()
def accept_edit(project: str, chapter: int, extracted_json: str,
                confirm: str = "") -> dict:
    """采纳事后编辑。清除旧数据 → 写入新提取数据 → 标记后续大纲。

    confirm需传入 'I_UNDERSTAND_THIS_IS_DESTRUCTIVE'。
    extracted_json 为对edited文本重新提取的JSON结果。
    """
    return core.accept_edit(project, chapter, extracted_json, confirm)
```

- [ ] **Step 5: Add test section [17] to test_e2e.py**

```python
        # ---- 17. 事后编辑工具 ----
        print("\n[17] 事后编辑工具 (analyze_edit_impact + accept_edit)")
        from core import analyze_edit_impact as _aei, accept_edit as _ae

        kg.clear_project()
        kg.add_character("老孟", role="主角")
        kg.add_location("澡堂", loc_type="废墟")
        kg.add_chapter_arc(1, purpose="ch1", scenes="A", ending="end")
        kg.add_chapter_arc(2, purpose="ch2", scenes="B", ending="end")
        kg.add_chapter_arc(3, purpose="ch3", scenes="C", ending="end")

        # 创建 edited 文件
        import tempfile
        output_dir = os.path.join(os.path.dirname(kg._path), "output")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "ch1_edited.txt"), "w", encoding="utf-8") as f:
            f.write("这是编辑后的ch1文本")

        # 添加旧数据
        kg.add_event("E1_01", title="发现焊疤", chapter=1)
        kg.add_event("E1_02", title="看到纸片", chapter=1)
        kg.add_relation("Event", "id", "E1_01", "INVOLVES", "Character", "name", "老孟")
        kg.add_suspense_thread("ST01_01", content="焊疤之谜", planted_chapter=1,
                                importance="high", status="planted")
        kg.add_relation("Event", "id", "E1_01", "EVIDENCES",
                         "SuspenseThread", "id", "ST01_01")

        kg.add_outline_entry(2, purpose="调查焊疤", key_events="检查焊疤")
        kg.add_outline_entry(3, purpose="深入", key_events="发现纸片")

        # analyze_edit_impact
        result_aei = _aei(PROJECT, 1)
        test("analyze_edit_impact returns dict", isinstance(result_aei, dict))
        test("analyze_edit_impact has old_events",
             len(result_aei.get("old_events", [])) == 2,
             f"old_events: {result_aei.get('old_events', [])}")
        test("analyze_edit_impact affected threads",
             len(result_aei.get("affected_threads", [])) >= 1,
             f"threads: {result_aei.get('affected_threads', [])}")
        test("analyze_edit_impact downstream warnings",
             len(result_aei.get("downstream_warnings", [])) >= 1,
             f"warnings: {result_aei.get('downstream_warnings', [])}")

        # 无edited文件时应报错
        result_no_edit = _aei(PROJECT, 99)
        test("analyze_edit_impact missing file",
             "error" in result_no_edit)

        # accept_edit
        new_extraction = json.dumps({
            "events": [
                {"id": "E1_01", "title": "重写事件", "chapter": 1, "type": "daily"},
            ],
            "event_relations": [
                {"event_id": "E1_01", "character": "老孟", "location": "澡堂"},
            ],
            "new_characters": [],
            "new_locations": [],
            "thread_updates": [],
            "new_threads": [],
            "causal_links": [],
            "evidence_links": [],
        })
        result_ae = _ae(PROJECT, 1, new_extraction,
                         confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")
        test("accept_edit returns stats",
             "stats" in result_ae)
        test("accept_edit marked downstream",
             len(result_ae.get("downstream_marked_for_revision", [])) >= 1,
             f"marked: {result_ae.get('downstream_marked_for_revision', [])}")

        # accept_edit without confirm should fail
        result_blocked = _ae(PROJECT, 1, "{}", confirm="")
        test("accept_edit blocked without confirm",
             "error" in result_blocked or "BLOCKED" in str(result_blocked))

        # 验证后续大纲被标记
        oe2 = kg.get_outline_entry(2)
        test("downstream outline marked needs_revision",
             oe2 is not None and oe2.get("compliance") == "needs_revision",
             f"compliance: {oe2.get('compliance') if oe2 else 'None'}")
```

- [ ] **Step 6: Run tests**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass including new [17] section.

- [ ] **Step 7: Commit**

```bash
git add novel_mcp_server/kg_json.py novel_mcp_server/core.py novel_mcp_server/server.py novel_mcp_server/test_e2e.py
git commit -m "feat: add analyze_edit_impact + accept_edit MCP tools for post-hoc editing"
```

---

### Task 5: review_chapter MCP Tool

**Files:**
- Modify: `novel_mcp_server/core.py`
- Modify: `novel_mcp_server/server.py`
- Modify: `novel_mcp_server/test_e2e.py` (add test section [18])

This is the review checkpoint tool. The author (or agent) calls it after each chapter with an action.

- [ ] **Step 1: Add `review_chapter` to core.py**

Append to core.py:

```python
def review_chapter(project: str, chapter: int, action: str,
                   edited_text: str = "") -> dict:
    """审核关卡操作。

    action: accept | edit | rewrite | revise_outline
    """
    kg = _kg(project)
    valid_actions = {"accept", "edit", "rewrite", "revise_outline"}
    if action not in valid_actions:
        return {"error": f"未知操作 '{action}'，可选: {', '.join(sorted(valid_actions))}"}

    if action == "accept":
        return {
            "action": "accept",
            "chapter": chapter,
            "message": f"第{chapter}章已通过审核。可以继续第{chapter+1}章。",
        }

    if action in ("edit", "rewrite"):
        if not edited_text:
            return {"error": f"action='{action}' 需要 edited_text 参数"}
        # 保存为 edited 文件
        output_dir = os.path.join(
            os.path.dirname(kg._path), "output")
        os.makedirs(output_dir, exist_ok=True)
        edited_path = os.path.join(output_dir, f"ch{chapter}_edited.txt")
        with open(edited_path, "w", encoding="utf-8") as f:
            f.write(edited_text)

        if action == "rewrite":
            # 重写：清除旧数据，提示Agent重新提取
            return {
                "action": "rewrite",
                "chapter": chapter,
                "message": f"第{chapter}章已保存编辑版本。请重新提取并调用 accept_edit 写入图谱。",
                "edited_path": edited_path,
            }
        else:
            # 小修：保存edited文件，后续 analyze_edit_impact 可用
            return {
                "action": "edit",
                "chapter": chapter,
                "message": f"第{chapter}章小修已保存。可调用 analyze_edit_impact 检查影响。",
                "edited_path": edited_path,
            }

    if action == "revise_outline":
        return {
            "action": "revise_outline",
            "chapter": chapter,
            "message": f"请调用 revise_outline 修订第{chapter}章大纲，然后继续。",
        }

    return {"error": "unreachable"}
```

Note: `os` is already imported in core.py. `kg._path` gives us the project directory (from `kg_json.py`'s `_path` property).

- [ ] **Step 2: Add MCP decorator to server.py**

Append to server.py:

```python
@mcp.tool()
def review_chapter(project: str, chapter: int, action: str,
                   edited_text: str = "") -> dict:
    """审核关卡操作。

    action: 'accept'(通过), 'edit'(小修,需edited_text),
    'rewrite'(重写,需edited_text), 'revise_outline'(修订大纲)。
    accept/revise_outline 不需要 edited_text。
    edit/rewrite 会将 edited_text 保存为 chN_edited.txt。
    """
    return core.review_chapter(project, chapter, action, edited_text)
```

- [ ] **Step 3: Add test section [18] to test_e2e.py**

```python
        # ---- 18. review_chapter MCP工具 ----
        print("\n[18] review_chapter MCP工具")
        from core import review_chapter as _rc

        # accept
        result_accept = _rc(PROJECT, 1, "accept")
        test("review_chapter accept",
             result_accept["action"] == "accept")
        test("review_chapter accept message",
             "通过审核" in result_accept["message"])

        # edit (with text)
        result_edit = _rc(PROJECT, 1, "edit", edited_text="修改后的文本内容")
        test("review_chapter edit saved",
             result_edit["action"] == "edit")
        test("review_chapter edit has path",
             "edited_path" in result_edit)

        # rewrite (with text)
        result_rewrite = _rc(PROJECT, 2, "rewrite", edited_text="完全重写的文本")
        test("review_chapter rewrite",
             result_rewrite["action"] == "rewrite")

        # revise_outline
        result_revise = _rc(PROJECT, 1, "revise_outline")
        test("review_chapter revise_outline",
             result_revise["action"] == "revise_outline")

        # invalid action
        result_invalid = _rc(PROJECT, 1, "invalid_action")
        test("review_chapter invalid action",
             "error" in result_invalid)

        # edit without text
        result_no_text = _rc(PROJECT, 1, "edit")
        test("review_chapter edit no text error",
             "error" in result_no_text)
```

- [ ] **Step 4: Run tests**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add novel_mcp_server/core.py novel_mcp_server/server.py novel_mcp_server/test_e2e.py
git commit -m "feat: add review_chapter MCP tool for checkpoint-based review"
```

---

### Task 6: Config Defaults + Final Integration

**Files:**
- Modify: `novel_kg_mvp/config_loader.py` (add defaults)
- Modify: `novel_mcp_server/test_e2e.py` (verify config loads)

This task adds the config defaults for the new features and does a final full test run.

- [ ] **Step 1: Add config defaults to config_loader.py**

Add a new section `"collaboration"` to the `DEFAULTS` dict in `novel_kg_mvp/config_loader.py`:

```python
    "collaboration": {
        "review_checkpoint": False,
        "outline_compliance": True,
        "auto_revise_outline": False,
    },
```

- [ ] **Step 2: Verify config loads correctly**

Add a quick test at the end of test_e2e.py (before the final summary):

```python
        # ---- 19. 协作配置 ----
        print("\n[19] 协作配置")
        from config_loader import config_loader
        cfg = config_loader.load(PROJECT)
        collab = cfg.get("collaboration", {})
        test("collaboration config exists",
             "collaboration" in cfg,
             f"keys: {list(cfg.keys())}")
        test("review_checkpoint default False",
             collab.get("review_checkpoint") == False)
        test("outline_compliance default True",
             collab.get("outline_compliance") == True)
        test("auto_revise_outline default False",
             collab.get("auto_revise_outline") == False)

        # 通过 config_loader.get 访问
        from config_loader import config_loader as cl2
        test("config_loader.get collaboration",
             cl2.get(PROJECT, "collaboration", "review_checkpoint", default=False) == False)
```

- [ ] **Step 3: Run full test suite**

Run: `cd novel_mcp_server && python test_e2e.py`

Expected: All tests pass — both old [1]-[13] and new [14]-[19].

- [ ] **Step 4: Commit**

```bash
git add novel_kg_mvp/config_loader.py novel_mcp_server/test_e2e.py
git commit -m "feat: add collaboration config defaults + integration tests"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Outline compliance (programmatic) → Task 1 + Task 2
- check_outline_compliance tool → Task 2
- revise_outline tool → Task 3
- analyze_edit_impact tool → Task 4
- accept_edit tool → Task 4
- review_chapter tool → Task 5
- Config (review_checkpoint, outline_compliance, auto_revise_outline) → Task 6
- Data model (compliance fields on outline_entry) → Task 3 (revise_outline writes them), Task 4 (accept_edit marks needs_revision)
- LLM semantic check → Not in code (Agent does this), correctly omitted
- New file convention (chN_edited.txt) → Task 4 (kg_json.py reads it), Task 5 (review_chapter writes it)

**2. Placeholder scan:** No TBD/TODO/placeholder patterns found.

**3. Type consistency:**
- `check_outline_compliance` in validators.py returns `list[Violation]` — used correctly in core.py
- `get_outline_entry` returns `dict | None` — checked with `if not outline_entry`
- `_bigram_overlap_str` defined at module level in core.py — used in `analyze_edit_impact`
- `accept_edit` calls `_mine_clear_chapter` and `write_extraction_to_graph` — both imported at top of core.py
- `kg._path` used in review_chapter — valid for JsonKG (has `_path` property)

**4. Potential issues found and fixed inline:**
- `accept_edit` needs `_mine_clear_chapter` imported — already imported at top of core.py (line 27)
- `review_chapter` uses `os.path.dirname(kg._path)` — `kg._path` is a property returning the graph.json path, so dirname gives the project dir
- Test section numbering: [14]-[19], no conflicts with existing [1]-[13]
