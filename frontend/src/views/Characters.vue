<!-- src/views/Characters.vue -->
<script setup lang="ts">
import { ref, watch, computed, h } from 'vue'
import {
  NSpin, NDataTable, NSelect, NSpace, NTag, NEmpty,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()

interface CharacterRow {
  id: number
  name: string
  pronoun: string | null
  gender: string | null
  role: string
  faction_id: number | null
  faction_name: string | null
  state: string
  personality: string | null
  goals: string | null
  abilities: string[]
  aliases: string[]
  secret_count: number
  knowledge_count: number
}

const rows = ref<CharacterRow[]>([])
const loading = ref(true)
const error = ref('')

const roleF = ref<string | null>(null)
const stateF = ref<string | null>(null)

const roleOptions = ['protagonist', 'supporting', 'antagonist', 'minor'].map(r => ({ label: r, value: r }))
const stateOptions = ['active', 'dormant', 'deceased', 'ascended', 'merged'].map(s => ({ label: s, value: s }))

// 徽章配色
const roleTypeMap: Record<string, 'success' | 'info' | 'error' | 'default'> = {
  protagonist: 'success',
  supporting: 'info',
  antagonist: 'error',
  minor: 'default',
}
function roleTagType(role: string): 'success' | 'info' | 'error' | 'default' {
  return roleTypeMap[role] ?? 'default'
}
const stateTypeMap: Record<string, 'success' | 'default' | 'error' | 'warning' | 'info'> = {
  active: 'success',
  dormant: 'default',
  deceased: 'error',
  ascended: 'warning',
  merged: 'info',
}
function stateTagType(state: string): 'success' | 'default' | 'error' | 'warning' | 'info' {
  return stateTypeMap[state] ?? 'default'
}

// personality 摘要：截断到 28 字
function excerpt(text: string | null): string {
  if (!text) return ''
  const t = text.trim()
  return t.length > 28 ? t.slice(0, 28) + '…' : t
}

async function load() {
  if (!props.wid) { loading.value = false; rows.value = []; return }
  loading.value = true
  error.value = ''
  try {
    rows.value = (await api.characters(props.wid)) as CharacterRow[]
  } catch (e: any) {
    error.value = e?.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}
watch(() => props.wid, load, { immediate: true })

// 前端过滤
const filtered = computed(() => {
  return rows.value.filter(r => {
    if (roleF.value && r.role !== roleF.value) return false
    if (stateF.value && r.state !== stateF.value) return false
    return true
  })
})

const columns = computed<DataTableColumns<CharacterRow>>(() => [
  {
    title: '姓名',
    key: 'name',
    width: 110,
    render: (row) => h('span', { class: 'cell-name' }, row.name),
  },
  {
    title: 'role',
    key: 'role',
    width: 110,
    render: (row) => h(NTag, { size: 'small', type: roleTagType(row.role), bordered: false }, { default: () => row.role }),
  },
  {
    title: 'state',
    key: 'state',
    width: 100,
    render: (row) => h(NTag, { size: 'small', type: stateTagType(row.state), bordered: false }, { default: () => row.state }),
  },
  {
    title: '代词',
    key: 'pronoun',
    width: 70,
    render: (row) => h('span', { class: 'cell-muted' }, row.pronoun || '—'),
  },
  {
    title: '派系',
    key: 'faction_name',
    width: 120,
    render: (row) => h('span', { class: 'cell-muted' }, row.faction_name || '—'),
  },
  {
    title: '性格摘要',
    key: 'personality',
    render: (row) => h('span', { class: 'cell-excerpt' }, excerpt(row.personality) || '—'),
  },
  {
    title: 'secrets',
    key: 'secret_count',
    width: 80,
    align: 'center',
    render: (row) => h('span', { class: 'cell-count' }, String(row.secret_count)),
  },
  {
    title: 'knowledge',
    key: 'knowledge_count',
    width: 90,
    align: 'center',
    render: (row) => h('span', { class: 'cell-count' }, String(row.knowledge_count)),
  },
])

// 本 Task 只读：点行暂 console.log（NDrawer 编辑表单留 Task 17）
function onRowClick(row: CharacterRow) {
  // eslint-disable-next-line no-console
  console.log('character row clicked:', row.id, row.name)
}

const rowProps = (row: CharacterRow) => ({
  style: 'cursor: pointer;',
  onClick: () => onRowClick(row),
})
</script>

<template>
  <div>
    <h2 style="color:#e6e9ef;margin-top:0">
      角色
      <small style="color:#7c8494;font-size:14px;margin-left:8px">{{ filtered.length }} / {{ rows.length }} 人</small>
    </h2>

    <NSpace style="margin-bottom:16px">
      <NSelect
        v-model:value="roleF"
        :options="roleOptions"
        placeholder="role"
        clearable
        style="width:160px"
      />
      <NSelect
        v-model:value="stateF"
        :options="stateOptions"
        placeholder="state"
        clearable
        style="width:140px"
      />
    </NSpace>

    <NSpin v-if="loading" />
    <div v-else-if="error" style="color:#e06c6c;padding:16px">加载失败：{{ error }}</div>
    <NEmpty v-else-if="!rows.length" description="无角色数据" />
    <NEmpty v-else-if="!filtered.length" description="无匹配（筛选条件过严）" />
    <NDataTable
      v-else
      :columns="columns"
      :data="filtered"
      :row-props="rowProps"
      :bordered="false"
      :single-line="false"
      size="small"
      class="char-table"
    />
  </div>
</template>

<style scoped>
:deep(.char-table) {
  background: #1a1d24;
}
/* 表头深色 */
:deep(.char-table .n-data-table-thead) {
  background: #20242d !important;
}
:deep(.char-table .n-data-table-th) {
  background: #20242d !important;
  color: #b8bfd0 !important;
  font-weight: 600;
}
:deep(.char-table .n-data-table-td) {
  background: #1a1d24;
  color: #e6e9ef;
}
:deep(.char-table .n-data-table-tr:hover .n-data-table-td) {
  background: rgba(78, 201, 176, 0.08) !important;
}
:deep(.char-table .n-data-table-tr:hover) {
  background: rgba(78, 201, 176, 0.08) !important;
}
.cell-name {
  color: #4ec9b0;
  font-weight: 600;
}
.cell-muted {
  color: #7c8494;
  font-size: 13px;
}
.cell-excerpt {
  color: #b8bfd0;
  font-size: 13px;
  line-height: 1.5;
}
.cell-count {
  color: #e6e9ef;
  font-variant-numeric: tabular-nums;
}
</style>
