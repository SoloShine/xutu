---
name: analyze-style
description: 对作品已导入的参考作品做 LLM 文风基调分析,产出定性文风指令并入库。触发:/analyze-style <作品标识>。自包含——读持久化参考样本,无需原文件。
triggers:
  - "/analyze-style"
---

# 文风基调分析(/analyze-style)

对作品工作台里**已导入的参考作品**,用 LLM 分析其写作基调(气质),产一段精炼中文文风指令,写入该作品的 `directive`(注入 ChapterWriter)。补统计指纹抓不到的"气质"层。

## 何时用
- 工作台「文风指纹」里导入了参考作品后(指纹是统计,缺定性基调)。
- 重新导入新参考后指令过时(`directive_stale=true`)。

## 参数
- `$1` = 作品标识(目录名,如 `voidwright`)。缺省→让用户指定,或从 `projects/` 列出可选。

## 流程(严格按序)

### 1. 解析项目路径
`projects/<$1>`。不存在→列出 `projects/` 下目录让用户选,停。

### 2. 读持久化参考样本
```bash
cd D:/novel_test && python -m src.bedrock show-reference-sample --project projects/<$1>
```
返回 JSON `{source, directive, directive_source, directive_stale, sample}`。
- `sample` 为空 → 停,告诉用户:"该作品未导入参考作品。请先在工作台「文风指纹」用文件选择框导入一本参考 txt。" 
- `directive_stale=true` → 提示"当前指令来自旧参考(`directive_source`),将重新分析覆盖。"

### 3. 派 agent 分析样本 → 指令
用 Agent 工具(general-purpose),prompt 要点:
- 把 `sample` 全文给 agent(它是该参考的中段代表性正文,~5000字)。
- 指明参考作品名(`source`)、题材(从样本/标题判断,如爽文/科幻/悬疑)。
- 要求:基于实际文本观察(句节奏/视角叙事/对白风格/修辞/语言质地/节奏张力),**抓"气质"**(口吻、网感、标志性句式、视角纪律),不要套模板、不要泛泛。
- 输出:**一段 100–180 字中文文风指令**,写成"写正文时应遵循的基调要求"口吻(给写作 agent 用)。只返回该段,无分析过程/围栏。

### 4. 落库
```bash
cd D:/novel_test && python -m src.bedrock set-style-directive \
  --project projects/<$1> --directive "<agent 返回的指令>" --source "<source>" --scope work
```
`--source` = 步骤2 的 `source`(标记指令来源,换参考时据此判 stale)。

### 5. 回报
- 贴出产出的指令给用户确认/润色。
- 告知"已写入作品级 directive,工作台「文风指令」框刷新可见;后续写章会注入"。

## 约束
- 纯读取 DB 样本 + 一次 agent + repo 写入。**不经裸 SQL**(set-style-directive 走 repo)。
- 不碰指纹/标量/旋钮,只更 directive + directive_source。
- 若用户想卷级指令:加 `--scope volume --volume <N>`(步骤4),样本仍读作品级。
