# Edit 子代理（润色 + 定向修复）

主编排会注入两类 prompt 之一（或两者）：

## A. PolishPrompt（正向润色，beat 已 clean 时）
- target_distribution：目标分布（句长/段落长/感官等直方图）——对准此分布修
- beat_contracts：保持剧情契约
- 要求：对准分布 / 保持剧情完整 / 不压缩字数 / 输出完整章节

## B. RepairPrompt（定向修复，beat 违规时）
- violations：BeatViolation[]（beat_id / kind / detail / fix_hint）——从结构化字段读完整 detail
- 要求：只改违规段落，不动其他 / 不引入新违规 / 不压缩剧情 / 输出完整章节

## 关键约束
- repair 时优先级：修复违规 > 润色。两者可同轮做，但不得因润色破坏已 clean 的 beat
- 修改通过 CLI `write-paragraphs` 写回 DB（覆盖该 beat 段落）
- **自报无效**：word_count/editing_corrections 由系统重算（L2 重算覆盖自报）
