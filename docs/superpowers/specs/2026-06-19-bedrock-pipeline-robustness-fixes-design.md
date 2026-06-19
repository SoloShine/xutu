# Bedrock V3 管线鲁棒性修复 — 设计文档

- **日期**:2026-06-19
- **背景**:vigilia《长明》卷一(ch1-12)创作测试暴露 7 个系统级设计缺陷
- **目标**:在单章管线前置确定性校验(便宜、抗博弈),卷审退回"最后安全网"角色;修复导出/watchdog/状态等行为 bug
- **影响作品**:vigilia(主)、voidwright / juedi / nanhai_gold(行为正向修复,不动已落盘正文)

---

## 缺陷清单与根因(已代码核实)

| # | 缺陷 | 根因(文件:行) |
|---|------|----------------|
| 1 | writer/Polish 工作日志、指标自评、文件路径泄漏进 `paragraph` 表 | **契约层**:`stripFences` 仅剥整段围栏,其余全交 commit-paragraphs 切段入库(正文与 agent 思考一视同仁);Polish 阶段要求推理指标→叙述泄入;prompt 未禁非正文输出、无定界符 |
| 2 | 角色名/地名跨章不一致(周执→周植/周直,北原→北院/北苑) | 全管线无专名白名单校验;Consistency 阶段(`bedrock-chapter.js:89`)仅 LLM,无确定性硬校验 |
| 3 | `chapter.status` 永远 `writing`,无 `completed` → 导出全跳过 | `__main__.py` 仅 `set_chapter_status("writing")`;`reader_commands.py:124/135` 导出按 `status='completed'` 过滤 |
| 4 | watchdog `drift_ratio=0.92` → `blocking=true` | `watchdog.py:71` 计 `advisory_drift != "{}"`(恒真,因 drift 快照总写入)而非真实 `drifted != []` |
| 5 | ch5 机翻腔、ch11 破次元词过界(Boss战/怪量) | `style_examples` 缺"风格化油腔 vs 出戏游戏术语"边界例 |
| 6 | 灵感池 writer 看不到;`consume_inspiration` 返回 None | boot-context 8 key 无 `inspirations`;`outline.py:consume_inspiration` 无 return |
| 7 | ch5 落盘却无 `chapter_review_flag` 行 | persist 路径未无条件 `ensure_flag`,ch5(1 轮修复)finalize 未写 flag |

---

## 单元 A — 写面防污染:契约优先 + 检测兜底(#1 + #7)

**根因(契约层)**:当前契约是"agent 吐什么 → `stripFences` 剥最外层围栏 → 剩下全部交 commit-paragraphs 切段入库"。commit-paragraphs 对正文与 agent 思考/日志一视同仁地切段,故后者被当正文入库。Polish/style-polish 阶段显式要求 agent 推理文风指标,使其必然叙述"我删了 N 个明喻、对白占比 X%",泄入正文流;prompt 又未禁止非正文输出,且无定界符可"只摘正文区"。

**修法**:白名单(定界提取)为主,黑名单(正则检测)为兜底,重试闭环保稳定。

### A0. 正文定界契约(主)

**约定**:ChapterWriter / Polish / style-polish / Repair / Consistency 等所有产正文 agent,必须把正文包进**带标签围栏** ` ```prose `:

```
```prose
<本章正文,逐 beat 段落>
```
```

- 只认 `prose` 标签围栏;普通 ``` 围栏**不算**(防 agent 把推理包进普通围栏)。
- `bedrock-chapter.js` 把 `stripFences` 升级为 `extractProse(raw)`,**只取 `prose` 标签区内容,区外一律丢弃**。

**`extractProse(raw)` 降级链(保输出稳定性)**:
1. **有 `prose` 标签区**:取内容;多个区取最长(正文是主体)。✅ 主路径。
2. **无标签区(agent 漏用)**:回退 `prose_hygiene.sanitize_prose`(见 A1)清洗;若清洗后 ≥ beat 数 且 ≥ 500 字 → 用之并 log 警告"agent 未用 prose 定界符,已回退清洗";否则进入 3。
3. **清洗仍不达标**:返回失败 → 触发 Repair 重试(≤3 轮,既有机制)。

**prompt 强化**(所有产正文模板,`chapter_writer.md` / `edit_agent.md` 等):
- "只输出 `prose` 围栏内的正文。无前言、无指标点评、无思考过程、无文件路径、无工作日志。围栏外任何文本将被系统忽略。"
- 因提取层真的会忽略围栏外,该指令**可信**,LLM 遵守率更高。
- Polish/style-polish 阶段:指标推理不进输出流(仅产 prose 块);若需留推理,放进围栏外(自动丢弃)。

### A1. prose_hygiene 检测(兜底,A0 第 2 步依赖)

**新组件** `src/bedrock/checks/prose_hygiene.py`(确定性,零 LLM):

- `META_PATTERNS`:覆盖实测泄漏签名的正则集合——
  - 指标自评:`指标|破折号|对话占比|修辞.{0,3}密度|明喻.{0,4}像|检查破折号`
  - 草案/润色汇报:`草案.{0,6}符合|润色版本|符合.{0,4}要求|我(删除|修改|调整)|唯一的顾虑`
  - 文件路径:`[A-Za-z]:[\\/]|projects/[^ ]*\.db|\.db\b`
  - 纯分隔符:`^(-{3,}|\*{3,}|\* \* \*|—{2,})$`
  - 代码块:`` `{3} ``
- `classify_paragraphs(paras) -> list[(seq, is_meta, matched)]`:逐段判定。
- `sanitize_prose(raw) -> (cleaned_text, removed_count, removed_preview)`:剥离所有 meta 段(leading/trailing/mid),返回清洗后正文 + 移除统计。

**commit-paragraphs 改造**(`__main__.py` handler,作为 A0 之外的写面镜像防线——防止绕过工作流直接调 CLI 时漏网):
- 正常路径:工作流 `extractProse` 已提取纯正文 → commit 直接切段入库。
- 防御路径:commit 仍对入参跑 `sanitize_prose`(替代当前仅 `_is_lead_junk` 剥头部),剥离任何残余 meta 段。
- 清洗后**剩余段数 < beat 数**,或**清洗后正文 < 500 字** → `sys.exit` 拒绝(整篇重度污染,强制重交)。阈值常量集中到 `prose_hygiene` 模块头。
- 保留 `_looks_like_worklog`(整篇)作为重度污染闸;`_WORKLOG_TOKENS` 补 `META_PATTERNS` 的关键 token,阈值降为"任一强特征命中"。

### A2. L2 non_prose 兜底(#1 第三层,数据库内最后防线)

**`src/bedrock/checks/beat_fulfillment.py`**(L2 规则集):
- 新增违规 kind `non_prose`:对已入库 `paragraph` 逐段跑 `prose_hygiene.detect_meta_paragraphs`,命中 → 违规条目 `{beat_id, kind:"non_prose", detail, fix_hint:"删除该 meta 段", para_seq}`。
- L2 hard_gate 已含"违规数==0 才过"语义,`non_prose` 自动纳入 → 即便 A0/A1 漏网,落盘后 L2 仍拦(Retry loop 兜底)。三层(A0 提取 / A1 清洗 / A2 L2)纵深。

### A3. flag 行保底(#7)

**`src/bedrock/orchestration/review_flag.py`** + persist 路径:
- `ensure_flag(conn, chapter_id)` 保持幂等(已存在,`INSERT OR IGNORE`)。
- Finalize relay / `verify-persisted` 末尾无条件调 `ensure_flag`,保证每章落盘即有 flag 行(即使 0 违规、0 drift)。
- 根因排查:ch5 经历 1 轮 L2 Repair,finalize 的 `mark_advisory_drift` 路径疑似被 repair 分支跳过——impl 时确认并在 persist 出口补 `ensure_flag`。

---

## 单元 B — 状态/导出生命周期(#3)

- **转换规则**(centralize 到 repo `set_chapter_status` 调用方):
  - `verify-persisted` 通过 → `mark_completed`(`set_chapter_status(completed)`)。
  - `commit-paragraphs` / `edit-paragraphs` 任意写入 → 自动回退 `writing`(已隐式;显式化 + 文档)。
  - 回退 `writing` 后,再次 verify-persisted 通过 → 再 `completed`。
- **新 CLI** `mark-completed --project <p> --chapter N`:兜底(人工/卷审批量)。
- 导出(`reader_commands.py`)无需改(已按 `completed` 过滤);book/volume/chapter 三级恢复产出。
- **不动**:volume-review 的 Fix 仍可编辑已 completed 章(其 edit-paragraphs 自动 reopen→writing,修完需重 verify)。

---

## 单元 C — watchdog drift(#4)

**`src/bedrock/orchestration/watchdog.py`**:
1. **bug 修**(line 69-75):`drift_nonempty` 改为计 `json.loads(advisory_drift).get("drifted")` 非空(等价 `ok == false`)的章数,而非 JSON 串非空。
2. **上限/下限区分**(bound 默认值集中到 `watchdog` 模块头,可调):
   - `upper` 指标(破折号密度、修辞密度、short_sent_rate):仅"实测 > 目标"算 drift。
   - `dialogue_ratio`:双向但宽松——实测落在目标的 [0.5×, 1.5×] 区间内不算 drift(母女戏/对手戏天然波动)。
   - `scalar_targets` / 指纹派生处(`style/extractor.py`、`template_repo`)为每维带 `bound`。
3. **卷级同向门控**:
   - 单章 drift 不直接进 blocking 比率。
   - 新判定:`drift_flagged` = 存在"连续 ≥3 章、同一指标、同一方向超阈"。
   - `WATCHDOG_DRIFT_RATIO` 重定义为该"同向连续段"占总章比(阈值调低,如 0.25)。
4. `blocking` 语义收紧:仅 hug_findings + 跨卷悬链 + 同向连续 drift。

---

## 单元 D — 专名硬校验(#2,分层)

**新 CLI** `check-proper-nouns --project <p> --chapter N`(确定性,零 LLM),Consistency 阶段作为 relay 调用(`bedrock-chapter.js` Consistency phase)。

**白名单**:DB `character.name` + `location.name`(+ `character.alias`/`location.alias` 若有)。

**检测**(`src/bedrock/checks/proper_nouns.py`):
- 形近/音近:`edit_distance_1` on 名字长度 ≥2;外加精选 confusable 表(植↔执、直↔执、院↔原、苑↔原,可扩展)。
- 扫 `paragraph.text`,定位变体出现(para_id, variant, candidates[])。

**两层处置**:
- **Tier-1(高置信)**:变体仅 1 个白名单候选,且该 canonical name 在**本章或前序章** `paragraph` 中已出现 ≥1 次(即既定专名,变体是笔误)→ 自动生成 `edit-paragraphs update` op 就地替换。
  - **留痕**:repo `edit-paragraphs` 自动记 `amendment`(old/new);另写 `chapter_review_flag.proper_noun_autoedit = {count, items:[{para_id, old, new}]}` **供卷审核对**。
- **Tier-2(低置信/多义)**:多候选、或变体本身是常用词(如"北院"可能是医院北院)→ **不自动改**,仅 escalate flag(detail 列出供人工/卷审判)。
- **原则**:自动改 = 高置信 + 必留 amendment + 必 flag 可复核;歧义项绝不自动碰。误伤面最小,且可追溯、可回退、可推翻。

**Consistency 阶段编排**:`bedrock-chapter.js` 在 LLM consistency agent 之后,跑 `check-proper-nouns` relay → apply tier-1 ops + 收集 tier-2 flag → 重 run-l2。

---

## 单元 E — 文风边界例(#5)

- vigilia `style_template.style_examples` 增第 6 对:
  - **good**:"弹幕式吐槽融入人物心理"示范(参考 ch1"这NPC怎么一来就怼主线的"——油腔服务于刻画林昭的清醒与疏离)。
  - **bad**:"Boss战/怪量/开大"纯游戏黑话破次元(参考 ch11 过界)——标签:✗ 出戏游戏术语(违反"油腔谐音梗须贴合本作世界观,勿跨次元")。
- chapter_writer 模板【风格示范】注入随正反例进 writer。内容补充,非代码逻辑。
- 经 repo `set_style_config(style_examples=...)` 写入(铁律)。

---

## 单元 F — 灵感池注入(#6)

- **boot-context**(`orchestration/boot_context.py`)增 `inspirations` key:注入 `status IN (raw,refined,partial)` 的灵感(`[{id, type, content}]`),作为 writer 可选素材池。
- **`consume_inspiration`**(`repositories/outline.py`)补 `return dict(row)`(修 None 坑)。
- 消费 curate 仍由编排按章命中决定(本次测试已验证);writer 现至少看得见池。

---

## 测试策略

- **单元测试**(pytest,每组件):
  - `extractProse`(workflow):构造"有 prose 围栏且前后带日志"、"无围栏纯 prose"、"无围栏混 meta"、"多个围栏"、"围栏内仍混 meta" 五类输入,断言提取/降级/拒绝正确。
  - `prose_hygiene`:ch2/3/6/8/10 实测泄漏片段作 fixture,断言全部命中。
  - `beat_fulfillment` non_prose:同 fixture。
  - `watchdog`:构造 drifted=[]/ok=true 的快照,断言不计入;构造连续 3 章同向,断言 drift_flagged。
  - `proper_nouns`:周植/周直/北院/北苑 fixture,断言 tier 分类 + tier-1 生成 op + tier-2 仅 flag。
  - status 转换:verify→completed、edit→writing、re-verify→completed。
- **端到端回归**:vigilia ch5(最脏:机翻腔已 rewrite + 专名错 + 无 flag)重跑 chapter 管线,断言:无 meta 段、专名修正留痕、flag 行存在、status=completed、export 产出。
- **既有作品回归**:voidwright 跑 `run-watchdog`,断言 drift_ratio 回落到真实值(此前误报)。

## 影响面与回退

- 改动文件:`src/bedrock/checks/{prose_hygiene,proper_nouns}.py`(新)、`checks/beat_fulfillment.py`、`__main__.py`、`orchestration/{watchdog,boot_context,review_flag,persist_gate}.py`、`style/{extractor,template_repo}.py`、`repositories/{outline,plot_tree}.py`、`.claude/workflows/bedrock-chapter.js`(`stripFences`→`extractProse` + Consistency 专名 hook)、`.claude/templates/bedrock/{chapter_writer,edit_agent}.md`(prose 围栏契约 + 边界例)。
- 既有作品已落盘 `paragraph` 不动;专名校验只对新写章生效;watchdog/status/export 对既有作品是行为修正。
- 回退:各单元独立,可按单元 revert。
