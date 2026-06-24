<!-- src/views/Runs.vue -->
<!-- 工作流运行监控（phase 2 实时可观测性）。
     左:最近 run 列表;右:Vue Flow 只读流程图(boot→write→revise→consistency→finalize),
     高亮当前/已访问节点;下:事件时间线。running 态自动轮询。
     数据由 runner(.js 薄发射 / 将来 LangGraph)边跑边写 workflow_run_event。 -->
<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { NSpin, NEmpty, NCard, NSpace, NTag, NButton, NSelect, useMessage } from 'naive-ui'
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
    runs.value = await api.runs(props.wid, 50, chapterFilter.value ?? undefined) as any
    if (!selectedId.value && runs.value.length) selectedId.value = runs.value[0].id
    if (selectedId.value && !runs.value.find(r => r.id === selectedId.value)) {
      selectedId.value = runs.value.length ? runs.value[0].id : null
    }
  } catch (e: any) { msg.error('加载 runs 失败: ' + (e.message || e)) }
}

async function loadRun() {
  if (selectedId.value == null) { run.value = null; events.value = []; return }
  try {
    const r = await api.run(props.wid, selectedId.value) as any
    run.value = r.run; events.value = r.events
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
</script>

<template>
  <NSpin :show="loading">
    <NSpace align="center" style="margin-bottom:12px">
      <strong>运行监控</strong>
      <NSelect v-model:value="chapterFilter" :options="([{ label: '全部章', value: null }, ...Array.from(new Set(runs.map(r => r.chapter_global).filter((x): x is number => x != null))).map(c => ({ label: '第' + c + '章', value: c }))] as any[])"
               size="small" style="width:140px" placeholder="按章过滤" />
      <NButton size="small" @click="refreshAll">↻ 刷新</NButton>
      <NTag v-if="runs.some(r => r.status === 'running')" size="small" type="info" :bordered="false">实时轮询中(2s)</NTag>
    </NSpace>

    <div class="runs-layout">
      <!-- 左:run 列表 -->
      <NCard size="small" class="runs-list" :content-style="{ background: 'var(--br-card)' }">
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
      </NCard>

      <!-- 右:流程图 + 时间线 -->
      <div class="runs-main">
        <NCard size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
          <div style="height:220px">
            <VueFlow :nodes="flowNodes" :edges="flowEdges" :nodes-draggable="false" :nodes-connectable="false"
                     :elements-selectable="false" :pan-on-drag="true" :zoom-on-scroll="true" fit-view-on-init>
              <Background :gap="20" :size="1" pattern-color="#888" />
            </VueFlow>
          </div>
        </NCard>

        <NCard title="事件时间线" size="small" :content-style="{ background: 'var(--br-card)' }">
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
  </NSpin>
</template>

<style scoped>
.runs-layout { display: grid; grid-template-columns: 260px 1fr; gap: 12px; }
.runs-list { max-height: 70vh; overflow-y: auto; }
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
