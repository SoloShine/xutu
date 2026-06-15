<!-- src/views/Outline.vue -->
<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import {
  NSpin, NCard, NTag, NTree, NSelect, NSpace, NEmpty, NButton,
} from 'naive-ui'
import { api } from '../api/client'
import BeatEdit from '../components/edit/BeatEdit.vue'
import MasterOutlineEdit from '../components/edit/MasterOutlineEdit.vue'

const props = defineProps<{ wid: string }>()

interface Beat {
  id: number
  sequence: number
  purpose?: string | null
  pov_name?: string | null
  scene_setting?: string | null
  status?: string | null
  deviation_note?: string | null
  paragraph_count?: number | null
  volume_id?: number | null
}
interface Chapter {
  id: number
  global_number: number
  title?: string | null
  status?: string | null
  beats?: Beat[] | null
}
interface VolumeOutline {
  status?: string | null
  locked_at?: string | null
  beat_contracts?: unknown[] | null
}
interface Volume {
  id: number
  number: number
  name?: string | null
  volume_type?: string | null
  status?: string | null
  theme_seeds?: string[] | null
  volume_outline?: VolumeOutline | null
  chapters: Chapter[]
}
interface MasterOutline {
  theme_evolution?: string | null
  key_arcs?: string[] | null
  key_milestones?: string[] | null
  rhythm_curve?: string | null
}
interface OutlineData {
  master_outline: MasterOutline | null
  volumes: Volume[]
}

const data = ref<OutlineData | null>(null)
const loading = ref(true)
const error = ref('')
const expandedKeys = ref<string[]>([])

async function load() {
  if (!props.wid) { loading.value = false; data.value = null; return }
  loading.value = true
  error.value = ''
  try {
    data.value = await api.outline(props.wid) as OutlineData
    // 默认展开所有卷级节点
    expandedKeys.value = (data.value?.volumes ?? []).map(v => `vol-${v.id}`)
  } catch (e: any) {
    error.value = e?.message || String(e)
    data.value = null
  } finally {
    loading.value = false
  }
}
watch(() => props.wid, load, { immediate: true })

// master_outline 卡片是否渲染：四个字段全空/null → 整卡不渲染
const master = computed<MasterOutline | null>(() => data.value?.master_outline ?? null)
const hasMaster = computed(() => {
  const m = master.value
  if (!m) return false
  return !!(m.theme_evolution || m.rhythm_curve ||
    (m.key_arcs && m.key_arcs.length) ||
    (m.key_milestones && m.key_milestones.length))
})

// 卷选择 NSelect：默认 0 = 全部
const selectedVid = ref<number>(0)
const volumeOptions = computed(() => [
  { label: '全部卷', value: 0 },
  ...(data.value?.volumes ?? []).map(v => ({
    label: `第${v.number}卷 ${v.name || ''}`,
    value: v.id,
  })),
])

// beat status 徽章配色
function beatStatusType(status?: string | null): 'default' | 'info' | 'success' | 'warning' | 'error' {
  switch (status) {
    case 'written': return 'success'
    case 'verified': return 'info'
    case 'deviated': return 'error'
    case 'overridden': return 'warning'
    default: return 'default' // planned / null
  }
}
function volStatusType(status?: string | null): 'default' | 'info' | 'success' | 'warning' {
  if (status === 'completed' || status === 'locked') return 'success'
  if (status === 'drafted' || status === 'writing') return 'info'
  if (status === 'planned') return 'warning'
  return 'default'
}

function pad2(n: number): string {
  return n < 10 ? '0' + n : String(n)
}

// 渲染单条 status tag
function statusTag(text: string, type: 'default' | 'info' | 'success' | 'warning' | 'error') {
  return h(NTag, { size: 'tiny', type, bordered: false, round: true }, { default: () => text })
}

// NTree 节点数据结构（label 用 renderLabel 渲染，这里仅存 kind + 引用）
type ONode = {
  key: string
  kind: 'vol' | 'ch' | 'beat'
  isLeaf?: boolean
  children?: ONode[]
  // vol
  v?: Volume
  // ch
  ch?: Chapter
  // beat
  b?: Beat
  // beat 所属卷 id（契约编辑需要）+ 卷锁定状态
  volumeId?: number
  volumeLocked?: boolean
}

// NTree 数据：把后端 outline → ONode 树
const treeData = computed<ONode[]>(() => {
  const volumes = data.value?.volumes ?? []
  const filtered = selectedVid.value
    ? volumes.filter(v => v.id === selectedVid.value)
    : volumes
  return volumesToNodes(filtered)
})

function volumesToNodes(volumes: Volume[]): ONode[] {
  return volumes.map(v => {
    const locked = v.volume_outline?.status === 'locked'
    return {
      key: `vol-${v.id}`,
      kind: 'vol' as const,
      v,
      children: (v.chapters ?? []).map(ch => ({
        key: `ch-${ch.id}`,
        kind: 'ch' as const,
        ch,
        children: (ch.beats ?? []).map(b => ({
          key: `beat-${ch.id}-${b.id}`,
          kind: 'beat' as const,
          b,
          volumeId: v.id,
          volumeLocked: locked,
          isLeaf: true,
        })),
        isLeaf: !(ch.beats && ch.beats.length),
      })),
    }
  })
}

// NTree label 渲染函数
function renderLabel({ option }: { option: any }): any {
  const o: ONode = option
  if (o.kind === 'vol' && o.v) {
    const v = o.v
    const head = [
      h('span', { class: 'vol-label' }, `📁 第${v.number}卷 · ${v.name || ''}`),
      v.volume_type ? h(NTag, { size: 'tiny', type: 'info', bordered: false, round: true }, { default: () => v.volume_type }) : null,
      v.status ? h(NTag, { size: 'tiny', type: volStatusType(v.status), bordered: false, round: true }, { default: () => v.status }) : null,
    ]
    const subParts: any[] = []
    const vo = v.volume_outline
    if (vo && vo.status) {
      const locked = vo.status === 'locked'
      subParts.push(h(NTag, {
        size: 'tiny', type: locked ? 'error' : 'default', bordered: false, round: true,
      }, { default: () => `锁:${vo.status}` }))
    }
    if (v.theme_seeds && v.theme_seeds.length) {
      for (const s of v.theme_seeds) {
        subParts.push(h(NTag, { size: 'tiny', type: 'warning', bordered: false, round: true }, { default: () => s }))
      }
    }
    const parts: any[] = [h('div', { class: 'vol-head' }, head)]
    if (subParts.length) parts.push(h('div', { class: 'vol-sub' }, subParts))
    return h('div', { class: 'vol-node' }, parts)
  }
  if (o.kind === 'ch' && o.ch) {
    const ch = o.ch
    return h('div', { class: 'ch-node' }, [
      h('span', { class: 'ch-label' }, `📄 ch${pad2(ch.global_number)} ${ch.title || ''}`),
      ch.status ? statusTag(ch.status, volStatusType(ch.status) as any) : null,
    ])
  }
  if (o.kind === 'beat' && o.b) {
    const b = o.b
    const isDev = b.status === 'deviated'
    const head = [
      h('span', { class: 'beat-label' }, `beat ${b.sequence}`),
      h(NTag, { size: 'tiny', type: beatStatusType(b.status), bordered: false, round: true }, { default: () => b.status || 'planned' }),
      b.pov_name ? h('span', { class: 'beat-pov' }, `· ${b.pov_name}`) : null,
      b.paragraph_count != null ? h('span', { class: 'beat-para' }, `¶${b.paragraph_count}`) : null,
      h(NButton, {
        size: 'tiny',
        quaternary: true,
        class: 'beat-edit-btn',
        onClick: (e: Event) => {
          e.stopPropagation()
          openBeat(b, o.volumeId, o.volumeLocked)
        },
      }, { default: () => '编辑' }),
    ]
    const parts: any[] = [h('div', { class: 'beat-head' }, head)]
    if (b.purpose) parts.push(h('div', { class: 'beat-purpose' }, b.purpose))
    if (isDev && b.deviation_note) {
      parts.push(h('div', { class: 'beat-deviation' }, `⚠ ${b.deviation_note}`))
    }
    return h('div', { class: 'beat-node' }, parts)
  }
  return ''
}

// ---- 编辑入口 ----
const beatEditShow = ref(false)
const editingBeat = ref<any>(null)
const editingVolumeLocked = ref(false)
const masterEditShow = ref(false)

function openBeat(b: Beat, volumeId: number | undefined, locked: boolean | undefined) {
  editingBeat.value = { ...b, volume_id: volumeId ?? b.volume_id ?? null }
  editingVolumeLocked.value = !!locked
  beatEditShow.value = true
}

function openMaster() {
  masterEditShow.value = true
}

function onSaved() {
  load()
}
</script>

<template>
  <div>
    <h2 style="color:#e6e9ef;margin-top:0">正文 · 大纲</h2>

    <NSpace style="margin-bottom:16px" align="center">
      <span style="color:#7c8494;font-size:13px">卷</span>
      <NSelect
        v-model:value="selectedVid"
        :options="volumeOptions"
        placeholder="选择卷"
        style="width:240px"
      />
      <span v-if="data" style="color:#7c8494;font-size:13px">
        {{ data.volumes.length }} 卷
      </span>
    </NSpace>

    <NSpin v-if="loading" />
    <div v-else-if="error" style="color:#e06c6c;padding:16px">加载失败：{{ error }}</div>
    <div v-else-if="!data" style="color:#7c8494;padding:16px">请从左侧选择一个作品。</div>
    <div v-else>
      <!-- 顶部 master_outline 卡片（字段全空则不渲染） -->
      <NCard
        v-if="hasMaster"
        class="section-card"
        size="small"
        style="margin-bottom:20px"
      >
        <template #header>
          <span class="section-title">主题大纲 · master_outline</span>
          <NButton size="tiny" quaternary style="margin-left:8px" @click="openMaster">编辑</NButton>
        </template>
        <div class="mo-grid">
          <div v-if="master?.theme_evolution" class="mo-row">
            <span class="mo-key">主题演进</span>
            <span class="mo-val">{{ master.theme_evolution }}</span>
          </div>
          <div v-if="master?.rhythm_curve" class="mo-row">
            <span class="mo-key">节奏曲线</span>
            <span class="mo-val">{{ master.rhythm_curve }}</span>
          </div>
          <div v-if="master?.key_arcs?.length" class="mo-row">
            <span class="mo-key">关键弧线</span>
            <NSpace :size="6">
              <NTag
                v-for="(a, i) in master.key_arcs"
                :key="'arc-' + i"
                size="small"
                type="info"
                :bordered="false"
                round
              >{{ a }}</NTag>
            </NSpace>
          </div>
          <div v-if="master?.key_milestones?.length" class="mo-row">
            <span class="mo-key">关键里程碑</span>
            <NSpace :size="6">
              <NTag
                v-for="(ms, i) in master.key_milestones"
                :key="'ms-' + i"
                size="small"
                type="success"
                :bordered="false"
                round
              >{{ ms }}</NTag>
            </NSpace>
          </div>
        </div>
      </NCard>

      <!-- 多级大纲树 -->
      <NCard class="section-card" size="small">
        <template #header><span class="section-title">卷 / 章 / Beat 大纲树</span></template>
        <NEmpty
          v-if="!treeData.length"
          description="无大纲数据（卷/章尚未规划）"
        />
        <NTree
          v-else
          :data="treeData"
          :expanded-keys="expandedKeys"
          :render-label="renderLabel"
          block-line
          expand-on-click
          :selectable="false"
          @update:expanded-keys="keys => expandedKeys = keys as string[]"
        />
      </NCard>
    </div>

    <!-- 编辑弹窗（始终挂载，wid 选定即可；beat/master 为 null 时组件内自处理） -->
    <BeatEdit
      v-model:show="beatEditShow"
      :wid="wid"
      :beat="editingBeat"
      :volume-locked="editingVolumeLocked"
      @saved="onSaved"
    />
    <MasterOutlineEdit
      v-model:show="masterEditShow"
      :wid="wid"
      :master="master"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.section-card {
  background: #1a1d24;
  border: 1px solid #2a2f3a;
}
.section-title {
  color: #e6e9ef;
  font-weight: 600;
}
:deep(.section-card .n-card-header__main) {
  color: #e6e9ef;
}

/* master_outline 卡片 */
.mo-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mo-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.mo-key {
  color: #7c8494;
  font-size: 13px;
  min-width: 80px;
  flex-shrink: 0;
  padding-top: 2px;
}
.mo-val {
  color: #b8bfd0;
  font-size: 13px;
  line-height: 1.6;
}

/* NTree 节点渲染（深色） */
:deep(.n-tree .n-tree-node) {
  color: #e6e9ef;
}
:deep(.n-tree .n-tree-node-content) {
  padding: 2px 0;
}
.vol-node {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.vol-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.vol-label {
  color: #4ec9b0;
  font-weight: 600;
}
.vol-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding-left: 4px;
}
.ch-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ch-label {
  color: #e6e9ef;
  font-weight: 500;
}
.beat-node {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.beat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.beat-label {
  color: #b8bfd0;
  font-size: 13px;
}
.beat-pov {
  color: #7c8494;
  font-size: 12px;
}
.beat-para {
  color: #56b6c2;
  font-size: 11px;
  margin-left: auto;
}
.beat-edit-btn {
  margin-left: 8px;
}
.beat-purpose {
  color: #7c8494;
  font-size: 12px;
  line-height: 1.5;
  padding-left: 8px;
  border-left: 2px solid #2a2f3a;
  margin: 2px 0;
  max-width: 600px;
}
.beat-deviation {
  color: #e06c6c;
  font-size: 12px;
  line-height: 1.5;
  padding-left: 8px;
  border-left: 2px solid #e06c6c;
  margin: 2px 0;
  font-style: italic;
}
</style>
