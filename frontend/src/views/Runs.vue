<!-- src/views/Runs.vue -->
<!-- 工作流运行监控（phase 2 实时可观测性）。
     左:最近 run 列表;右:Vue Flow 只读流程图(boot→write→revise→consistency→finalize),
     高亮当前/已访问节点;下:事件时间线。running 态自动轮询。
     数据由 runner(.js 薄发射 / 将来 LangGraph)边跑边写 workflow_run_event。 -->
<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { NSpin, NEmpty, NCard, NSpace, NTag, NButton, NSelect, NSwitch, useMessage } from 'naive-ui'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()

interface RunSummary { id: number; chapter_global: number | null; volume_id: number | null; runner: string; status: string; current_node: string; started_at: string; ended_at: string | null; event_count: number }
interface RunEvent { id: number; seq: number; node: string; kind: string; payload: Record<string, any>; ts: string }

const runs = ref<RunSummary[]>([])
const selectedId = ref<number | null>(null)
const run = ref<{ status: string; current_node: string; chapter_global: number | null; started_at: string; ended_at: string | null } | null>(null)
const events = ref<RunEvent[]>([])
const telemetry = ref<any>(null)
const chapters = ref<{ global_number: number; title: string; status: string; volume_id: number }[]>([])
const triggerChapter = ref<number | null>(null)
const triggerDryRun = ref(false)
const starting = ref(false)
const loading = ref(true)
const chapterFilter = ref<number | null>(null)
let pollTimer: any = null

// 固定流程图节点(横向管线)
const PIPELINE = ['boot', 'write', 'revise', 'consistency', 'finalize']
const NODE_LABELS: Record<string, string> = {
  boot: 'Boot', write: 'Write(自纠结构)', revise: 'Revise(自纠)', consistency: 'Consistency', finalize: 'Finalize(verify)',
}
const baseNodes = PIPELINE.map((id, i) => ({
  id, position: { x: i * 200, y: 80 }, data: { label: NODE_LABELS[id] }, class: 'br-node',
}))
const baseEdges = PIPELINE.slice(0, -1).map((id, i) => ({
  id: `${id}-${PIPELINE[i + 1]}`, source: id, target: PIPELINE[i + 1], class: 'br-edge',
}))

// 已访问节点 = 事件中出现过的 pipeline 节点
const visited = computed(() => new Set(events.value.filter(e => PIPELINE.includes(e.node)).map(e => e.node)))
// 当前节点 = run.current_node(若属 pipeline),否则回退最近访问的
const activeNode = computed(() => {
  const cur = run.value?.current_node
  if (cur && PIPELINE.includes(cur)) return cur
  const vis = [...visited.value]
  return vis.length ? vis[vis.length - 1] : null
})

const flowNodes = computed(() => baseNodes.map(n => ({
  ...n,
  class: ['br-node',
    n.id === activeNode.value ? 'br-node-active' : '',
    visited.value.has(n.id) && n.id !== activeNode.value ? 'br-node-done' : ''].join(' '),
})))
const flowEdges = computed(() => baseEdges)

async function loadRuns() {
  try {
    const [rs, chs] = await Promise.all([api.runs(props.wid, 50, chapterFilter.value ?? undefined) as any,
                                          api.chapters(props.wid) as any])
    runs.value = rs
    chapters.value = chs || []
    if (!triggerChapter.value && chapters.value.length) triggerChapter.value = chapters.value[0].global_number
    if (!selectedId.value && runs.value.length) selectedId.value = runs.value[0].id
    if (selectedId.value && !runs.value.find(r => r.id === selectedId.value)) {
      selectedId.value = runs.value.length ? runs.value[0].id : null
    }
  } catch (e: any) { msg.error('加载 runs 失败: ' + (e.message || e)) }
}

const chapterOpts = () => chapters.value.map(c => ({
  label: `第${c.global_number}章 ${c.title || ''} [${c.status}]`, value: c.global_number,
})) as any[]

async function startRun() {
  if (triggerChapter.value == null) { msg.warning('选一章'); return }
  const ch = chapters.value.find(c => c.global_number === triggerChapter.value)
  starting.value = true
  try {
    const r = await api.startRun(props.wid, { chapter: triggerChapter.value, dry_run: triggerDryRun.value }) as any
    msg.success(`已触发第${triggerChapter.value}章 ${triggerDryRun.value ? '(dry-run)' : ''}(${(ch as any)?.status === 'writing' ? '重写' : '续写/写'})`)
    await refreshAll()
  } catch (e: any) { msg.error('触发失败: ' + (e.message || e)) }
  finally { starting.value = false }
}

async function loadRun() {
  if (selectedId.value == null) { run.value = null; events.value = []; telemetry.value = null; return }
  try {
    const r = await api.run(props.wid, selectedId.value) as any
    run.value = r.run; events.value = r.events; telemetry.value = r.telemetry ?? null
  } catch (e: any) { msg.error('加载 run 失败: ' + (e.message || e)) }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await loadRuns()      // 列表可能新增 / 状态变完成
    await loadRun()       // 当前 run 事件增长
  }, 2000)
}
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

async function refreshAll() {
  loading.value = true
  await loadRuns(); await loadRun()
  loading.value = false
  // 任何 run 在 running → 轮询;否则停
  if (runs.value.some(r => r.status === 'running')) startPolling(); else stopPolling()
}

watch(() => props.wid, refreshAll, { immediate: true })
watch(selectedId, loadRun)
watch(chapterFilter, refreshAll)
onUnmounted(stopPolling)

function statusType(s: string): 'success' | 'info' | 'error' | 'warning' {
  return s === 'completed' ? 'success' : s === 'failed' ? 'error' : s === 'aborted' ? 'warning' : 'info'
}
function payloadSummary(p: Record<string, any>): string {
  const keys = Object.keys(p)
  if (!keys.length) return ''
  return keys.map(k => `${k}=${JSON.stringify(p[k])}`).join(' ')
}
function fmtTokens(n: any): string {
  if (n == null) return '-'
  const x = Number(n); if (!isFinite(x)) return String(n)
  return x >= 1000 ? (x / 1000).toFixed(1) + 'k' : String(x)
}
function fmtMs(ms: any): string {
  if (ms == null) return '-'
  const s = Number(ms) / 1000; if (!isFinite(s)) return String(ms)
  return s >= 60 ? Math.round(s / 60) + '分' + Math.round(s % 60) + '秒' : s.toFixed(1) + '秒'
}
const PROC_LABELS: Record<string, string> = {
  write: 'Write', revise: 'Revise', consistency: 'Consistency',
}
</script>

<template>
  <div class="runs-wrap">
   <NSpin :show="loading" style="height:100%">
    <div class="runs-inner">
      <div class="runs-header">
        <NSpace align="center">
          <strong>运行监控</strong>
          <NSelect v-model:value="chapterFilter" :options="([{ label: '全部章', value: null }, ...Array.from(new Set(runs.map(r => r.chapter_global).filter((x): x is number => x != null))).map(c => ({ label: '第' + c + '章', value: c }))] as any[])"
                   size="small" style="width:140px" placeholder="按章过滤" />
          <NButton size="small" @click="refreshAll">↻ 刷新</NButton>
          <NTag v-if="runs.some(r => r.status === 'running')" size="small" type="info" :bordered="false">实时轮询中(2s)</NTag>
        </NSpace>
      </div>

      <div class="runs-layout">
        <!-- 左:run 列表 -->
        <NCard size="small" class="runs-list-card" :content-style="{ background: 'var(--br-card)', padding: '10px', height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }">
          <div class="runs-list">
            <NEmpty v-if="!runs.length" description="暂无运行记录(runner 未发射或未跑)" size="small" />
            <div v-for="r in runs" :key="r.id" class="run-item" :class="{ active: r.id === selectedId }" @click="selectedId = r.id">
              <div class="run-head">
                <span class="run-id">#{{ r.id }}</span>
                <NTag size="tiny" :type="statusType(r.status)" :bordered="false">{{ r.status }}</NTag>
              </div>
              <div class="run-meta">第{{ r.chapter_global ?? '-' }}章 · {{ r.event_count }} 事件 · {{ r.runner }}</div>
              <div class="run-meta">▸ {{ r.current_node || 'start' }}</div>
              <div class="run-ts">{{ r.started_at }}</div>
            </div>
          </div>
        </NCard>

        <!-- 右:触发写作 + 流程图 + 遥测 + 时间线 -->
        <div class="runs-main">
          <NCard title="触发写作" size="small" class="r-card" :content-style="{ background: 'var(--br-card)' }">
            <div class="hint" style="margin-bottom:8px">
              选已有章节(需有 beat 契约)→ runner 异步跑,事件实时出现在下方。「writing」章会重写;「completed」会覆盖;新章需先在 DB 建章+beat。
            </div>
            <NSpace align="center" :size="8">
              <NSelect v-model:value="triggerChapter" :options="chapterOpts()" placeholder="选章节"
                       size="small" filterable style="min-width:280px" />
              <span class="hint">dry-run</span>
              <NSwitch v-model:value="triggerDryRun" size="small" />
              <NButton type="primary" size="small" :loading="starting" :disabled="triggerChapter==null" @click="startRun">
                {{ triggerDryRun ? 'dry-run 跑通' : '开始写作' }}
              </NButton>
              <NTag v-if="runs.some(r => r.status==='running')" size="tiny" type="warning" :bordered="false">有 run 进行中(start_run 会复用)</NTag>
            </NSpace>
          </NCard>

          <NCard size="small" class="r-card" :content-style="{ background: 'var(--br-card)' }">
            <div style="height:220px">
              <VueFlow :nodes="flowNodes" :edges="flowEdges" :nodes-draggable="false" :nodes-connectable="false"
                       :elements-selectable="false" :pan-on-drag="true" :zoom-on-scroll="true" fit-view-on-init>
                <Background :gap="20" :size="1" pattern-color="#888" />
              </VueFlow>
            </div>
          </NCard>

          <NCard v-if="telemetry" title="LLM 遥测(成本核算)" size="small" class="r-card" :content-style="{ background: 'var(--br-card)' }">
            <div class="tel-summary">
              <span><strong>{{ telemetry.llm_calls }}</strong> 次 LLM 调用</span>
              <span>入 <strong>{{ fmtTokens(telemetry.tokens_in) }}</strong> token</span>
              <span>出 <strong>{{ fmtTokens(telemetry.tokens_out) }}</strong> token</span>
              <span>LLM 耗时 <strong>{{ fmtMs(telemetry.llm_time_ms) }}</strong></span>
              <span v-if="telemetry.run_duration_s != null">总 <strong>{{ fmtMs(telemetry.run_duration_s * 1000) }}</strong></span>
            </div>
            <div v-if="telemetry.by_process && Object.keys(telemetry.by_process).length" class="tel-procs">
              <div v-for="(p, key) in telemetry.by_process" :key="key" class="tel-proc">
                <span class="tel-proc-name">{{ PROC_LABELS[String(key)] || key }}</span>
                <span class="tel-proc-model">{{ p.endpoint }}/{{ p.model || '?' }}</span>
                <span>{{ p.calls }}× · 入{{ fmtTokens(p.tokens_in) }} 出{{ fmtTokens(p.tokens_out) }} · {{ fmtMs(p.latency_ms) }}</span>
              </div>
            </div>
            <div v-else class="tel-empty">无 LLM 调用(dry-run 或纯确定性章)</div>
          </NCard>

          <NCard title="事件时间线" size="small" class="r-card ev-card"
                 :content-style="{ background: 'var(--br-card)', display: 'flex', flexDirection: 'column', minHeight: '0', flex: '1', overflowY: 'auto', padding: '8px 12px 12px' }">
            <NEmpty v-if="!events.length" description="选中一个 run 查看事件" size="small" />
            <div v-for="e in events" :key="e.id" class="ev-row">
              <span class="ev-seq">{{ e.seq }}</span>
              <NTag size="tiny" :type="e.kind === 'error' ? 'error' : e.kind === 'l2_verdict' ? (e.payload.passed ? 'success' : 'warning') : 'info'"
                    :bordered="false">{{ e.node }}</NTag>
              <span class="ev-kind">{{ e.kind }}</span>
              <span class="ev-payload">{{ payloadSummary(e.payload) }}</span>
              <span class="ev-ts">{{ e.ts }}</span>
            </div>
          </NCard>
        </div>
      </div>
    </div>
   </NSpin>
  </div>
</template>

<style scoped>
.runs-wrap { height: 100%; min-height: 0; }
.runs-wrap :deep(.n-spin-container) { height: 100%; }
.runs-wrap :deep(.n-spin-content) { height: 100%; }
.runs-inner { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.runs-header { flex-shrink: 0; margin-bottom: 10px; }
.runs-layout { flex: 1; min-height: 0; display: grid; grid-template-columns: 260px 1fr; gap: 12px; }
/* 左:run 列表卡铺满 + 内部滚动 */
.runs-list-card { display: flex; flex-direction: column; min-height: 0; }
.runs-list-card :deep(.n-card-content) { display: flex; flex-direction: column; min-height: 0; }
.runs-list { flex: 1; min-height: 0; overflow-y: auto; }
/* 右:主区铺满,各卡 content-sized,事件时间线 flex:1 限高滚动 */
.runs-main { display: flex; flex-direction: column; gap: 12px; min-height: 0; height: 100%; }
.r-card { flex-shrink: 0; }
.ev-card { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.run-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; border: 1px solid var(--br-border-soft); margin-bottom: 6px; }
.run-item:hover { background: var(--br-elevated, var(--br-sider)); }
.run-item.active { border-color: var(--br-primary); background: var(--br-elevated, var(--br-sider)); }
.run-head { display: flex; justify-content: space-between; align-items: center; }
.run-id { font-weight: 600; color: var(--br-text1); }
.run-meta { font-size: 12px; color: var(--br-text2); margin-top: 2px; }
.run-ts { font-size: 10px; color: var(--br-text3); margin-top: 2px; }
.ev-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--br-border-soft); font-size: 12px; }
.ev-seq { width: 24px; color: var(--br-text3); text-align: right; }
.ev-kind { color: var(--br-text2); }
.ev-payload { flex: 1; color: var(--br-text3); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-ts { color: var(--br-text3); font-size: 10px; }
.tel-summary { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--br-text2); margin-bottom: 8px; }
.tel-summary strong { color: var(--br-text1); }
.tel-procs { display: flex; flex-direction: column; gap: 4px; }
.tel-proc { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--br-text3); border-top: 1px solid var(--br-border-soft); padding-top: 4px; }
.tel-proc-name { font-weight: 600; color: var(--br-text1); min-width: 76px; }
.tel-proc-model { color: var(--br-text2); font-family: monospace; font-size: 11px; }
.tel-empty { font-size: 12px; color: var(--br-text3); }
</style>

<!-- Vue Flow 节点主题化(非 scoped,穿透 VueFlow 内部)。
     Vue Flow 把 node.class 与 vue-flow__node-default 全堆在同一元素,故用同元素选择器(非后代)。 -->
<style>
.vue-flow__node.br-node { font-size: 12px; background: var(--br-card); color: var(--br-text2); border: 1px solid var(--br-border); }
.vue-flow__node.br-node-done { background: var(--br-card); color: var(--br-text1); border-color: var(--br-primary); }
.vue-flow__node.br-node-active {
  background: var(--br-primary); color: #fff; border-color: var(--br-primary); font-weight: 600;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--br-primary) 30%, transparent);
}
.vue-flow__node.br-node .vue-flow__node-resizer { display: none; }
.vue-flow__edge.br-edge .vue-flow__edge-path { stroke: var(--br-border); }
</style>
