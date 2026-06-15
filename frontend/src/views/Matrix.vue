<!-- src/views/Matrix.vue -->
<script setup lang="ts">
import { ref, watch, computed, h } from 'vue'
import {
  NSpin, NDataTable, NSelect, NSpace, NEmpty, NButton,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import BeatDrawer from '../components/BeatDrawer.vue'

const props = defineProps<{ wid: string }>()

interface VolumeOpt { id: number; name: string; number: number }
interface MatrixChar { id: number; name: string }
interface MatrixChapter { id: number; global_number: number; title: string; povs: number[] }
interface MatrixData {
  volume_name: string
  characters: MatrixChar[]
  chapters: MatrixChapter[]
}

const overview = ref<{ volume_list: VolumeOpt[] } | null>(null)
const volumes = ref<VolumeOpt[]>([])
const vid = ref<number | null>(null)
const volumeOptions = computed(() => volumes.value.map(v => ({ label: v.name, value: v.id })))

const data = ref<MatrixData | null>(null)
const loading = ref(true)
const error = ref('')

// BeatDrawer 状态
const drawerShow = ref(false)
const drawerChapter = ref<number | null>(null)
const drawerCharacter = ref<number | null>(null)
const drawerCharName = ref('')

async function loadOverview() {
  if (!props.wid) return
  try {
    overview.value = await api.overview(props.wid) as any
    volumes.value = (overview.value?.volume_list ?? []).map(v => ({ id: v.id, name: v.name, number: v.number }))
    if (vid.value == null && volumes.value.length) vid.value = volumes.value[0].id
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
}

async function loadMatrix() {
  if (!props.wid || vid.value == null) { loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    data.value = (await api.matrix(props.wid, vid.value)) as MatrixData
  } catch (e: any) {
    error.value = e?.message || String(e)
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.wid, loadOverview, { immediate: true })
watch(() => props.wid, loadMatrix, { immediate: true })
watch(vid, loadMatrix)

const noPov = computed(() => !!(data.value && data.value.characters.length === 0))

const columns = computed<DataTableColumns<MatrixChapter>>(() => {
  if (!data.value) return []
  const chars = data.value.characters
  const cols: DataTableColumns<MatrixChapter> = [
    {
      title: '章节',
      key: 'chapter',
      fixed: 'left',
      width: 180,
      render: (row) => h('span', { class: 'cell-chap' }, [
        h('span', { class: 'gnum' }, '第' + row.global_number + '章'),
        h('span', { class: 'ctitle' }, row.title || '—'),
      ]),
    },
  ]
  for (const ch of chars) {
    cols.push({
      title: ch.name,
      key: 'c' + ch.id,
      align: 'center',
      render: (row) => {
        if (row.povs.includes(ch.id)) {
          return h(NButton, {
            text: true,
            class: 'pov-dot',
            onClick: () => openDrawer(row.id, ch.id, ch.name),
          }, { default: () => '●' })
        }
        return h('span', { class: 'cell-empty' }, '')
      },
    })
  }
  // 合计列
  cols.push({
    title: '合计',
    key: 'total',
    width: 70,
    align: 'center',
    render: (row) => {
      const n = row.povs.length
      return h('span', { class: n ? 'cell-count' : 'cell-muted' }, String(n))
    },
  })
  return cols
})

const rows = computed(() => data.value?.chapters ?? [])

function openDrawer(chapterId: number, characterId: number, name: string) {
  drawerChapter.value = chapterId
  drawerCharacter.value = characterId
  drawerCharName.value = name
  drawerShow.value = true
}
</script>

<template>
  <div>
    <h2 style="color:#e6e9ef;margin-top:0">POV 矩阵</h2>

    <NSpace style="margin-bottom:16px" align="center">
      <span style="color:#7c8494;font-size:13px">卷</span>
      <NSelect
        v-model:value="vid"
        :options="volumeOptions"
        placeholder="选择卷"
        style="width:220px"
      />
      <span v-if="data" style="color:#7c8494;font-size:13px">
        {{ data.volume_name }} · {{ rows.length }} 章 · {{ data.characters.length }} POV 角色
      </span>
    </NSpace>

    <NSpin v-if="loading" />
    <div v-else-if="error" style="color:#e06c6c;padding:16px">加载失败：{{ error }}</div>
    <NEmpty v-else-if="!data || noPov" description="该卷无 POV 数据（无角色/无 beat）" />
    <NEmpty v-else-if="!rows.length" description="该卷无章节" />
    <NDataTable
      v-else
      :columns="columns"
      :data="rows"
      :bordered="false"
      :single-line="false"
      size="small"
      class="mx-table"
    />

    <BeatDrawer
      v-model:show="drawerShow"
      :wid="props.wid"
      :chapter="drawerChapter"
      :character="drawerCharacter"
      :character-name="drawerCharName"
    />
  </div>
</template>

<style scoped>
:deep(.mx-table) {
  background: #1a1d24;
}
:deep(.mx-table .n-data-table-thead) {
  background: #20242d !important;
}
:deep(.mx-table .n-data-table-th) {
  background: #20242d !important;
  color: #b8bfd0 !important;
  font-weight: 600;
}
:deep(.mx-table .n-data-table-td) {
  background: #1a1d24;
  color: #e6e9ef;
}
:deep(.mx-table .n-data-table-tr:hover .n-data-table-td) {
  background: rgba(78, 201, 176, 0.08) !important;
}
.cell-chap {
  display: inline-flex;
  flex-direction: column;
  line-height: 1.4;
}
.cell-chap .gnum {
  color: #4ec9b0;
  font-weight: 600;
  font-size: 13px;
}
.cell-chap .ctitle {
  color: #b8bfd0;
  font-size: 12px;
}
:deep(.pov-dot) {
  color: #4ec9b0 !important;
  font-size: 18px;
  line-height: 1;
  transition: transform 0.12s ease;
}
:deep(.pov-dot:hover) {
  transform: scale(1.4);
}
.cell-empty {
  display: inline-block;
}
.cell-count {
  color: #e6e9ef;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.cell-muted {
  color: #7c8494;
}
</style>
