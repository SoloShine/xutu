<!-- src/views/Overview.vue -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NSpin, NGrid, NGridItem, NStatistic, NCard, NTag, NEmpty, NSpace,
  NInput, NDynamicTags, NButton, useMessage,
} from 'naive-ui'
import { api } from '../api/client'
import { usePanels } from '../stores/panels'
import WorldbookInline from '../components/edit/WorldbookInline.vue'

const props = defineProps<{ wid: string }>()
const panels = usePanels()

interface Overview {
  name?: string
  volumes: number
  chapters: { completed: number; writing: number; total: number }
  characters: number
  word_total: number
  inspirations: { raw: number; refined: number; consumed: number; partial: number; discarded: number }
  volume_list: Array<{ id: number; number: number; name: string; volume_type: string; status: string; chapter_count: number; theme_seeds: string[] }>
  character_snapshot: Array<{ id: number; name: string; role: string; state: string; pronoun: string; personality_excerpt: string }>
  worldbook: {
    locations: Array<{ id: number; name: string; loc_type: string; description: string; state: string }>
    themes: Array<{ name: string; description: string; evolution: string }>
    motifs: Array<{ name: string; meaning: string; evolution: string }>
  }
}

const data = ref<Overview | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  if (!props.wid) { loading.value = false; data.value = null; return }
  loading.value = true
  error.value = ''
  try {
    data.value = await api.overview(props.wid) as Overview
  } catch (e: any) {
    error.value = e?.message || String(e)
    data.value = null
  } finally {
    loading.value = false
  }
}
watch(() => props.wid, load, { immediate: true })

// role 徽章配色：protagonist/supporting/antagonist/minor
const roleType: Record<string, 'success' | 'info' | 'error' | 'default'> = {
  protagonist: 'success',
  supporting: 'info',
  antagonist: 'error',
  minor: 'default',
}
function roleTagType(role: string): 'success' | 'info' | 'error' | 'default' {
  return roleType[role] ?? 'default'
}

// 卷 status 徽章配色
function volStatusType(status: string): 'default' | 'info' | 'success' | 'warning' {
  if (status === 'completed' || status === 'locked') return 'success'
  if (status === 'drafted' || status === 'writing') return 'info'
  if (status === 'planned') return 'warning'
  return 'default'
}

const inspItems = (d: Overview) => [
  { key: 'raw', label: 'raw', n: d.inspirations.raw, type: 'default' as const },
  { key: 'refined', label: 'refined', n: d.inspirations.refined, type: 'info' as const },
  { key: 'consumed', label: 'consumed', n: d.inspirations.consumed, type: 'success' as const },
  { key: 'partial', label: 'partial', n: d.inspirations.partial, type: 'warning' as const },
  { key: 'discarded', label: 'discarded', n: d.inspirations.discarded, type: 'error' as const },
]

function goCharacters() { panels.setFocusedView('characters') }

// ---- 卷名 / theme_seeds 内联编辑 ----
const msg = useMessage()
// 卷名编辑态：volume_id -> 是否编辑；草稿
const volNameEditing = ref<Record<number, boolean>>({})
const volNameDraft = ref<Record<number, string>>({})

function startVolName(v: { id: number; name: string; number: number }) {
  volNameEditing.value[v.id] = true
  volNameDraft.value[v.id] = v.name || ('卷' + v.number)
}
async function saveVolName(v: { id: number; name: string; number: number }) {
  if (!props.wid || !data.value) return
  const nm = (volNameDraft.value[v.id] || '').trim()
  if (!nm) { msg.error('卷名不能为空'); return }
  try {
    const res = await api.patch(props.wid, 'volumes', v.id, { name: nm })
    if (res && res.ok === false) { msg.error(res.error || '保存失败'); return }
    msg.success('已保存卷名')
    v.name = nm
    volNameEditing.value[v.id] = false
  } catch (e: any) {
    msg.error(e?.message || String(e))
  }
}
function cancelVolName(v: { id: number }) {
  volNameEditing.value[v.id] = false
}

// theme_seeds：NDynamicTags 直接驱动，变化即保存
async function onSeedsChange(v: { id: number; name: string; theme_seeds: string[] }, seeds: string[]) {
  if (!props.wid || !data.value) return
  try {
    const res = await api.patch(props.wid, 'volumes', v.id, { theme_seeds: seeds })
    if (res && res.ok === false) { msg.error(res.error || '保存失败'); return }
    msg.success('已保存 theme_seeds')
    v.theme_seeds = seeds
  } catch (e: any) {
    msg.error(e?.message || String(e))
  }
}
</script>

<template>
  <div>
    <h2 style="color:#e6e9ef;margin-top:0">
      总览
      <small v-if="data?.name" style="color:#7c8494;font-size:14px;margin-left:8px">{{ data.name }}</small>
    </h2>

    <NSpin v-if="loading" />
    <div v-else-if="error" style="color:#e06c6c;padding:16px">加载失败：{{ error }}</div>
    <div v-else-if="!data" style="color:#7c8494;padding:16px">请从左侧选择一个作品。</div>
    <div v-else>
      <!-- 统计网格 -->
      <NGrid :cols="'1 600:3 900:6'" :x-gap="12" :y-gap="12" style="margin-bottom:20px">
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="卷数" :value="data.volumes" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="章·已完成" :value="data.chapters.completed" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="章·写作中" :value="data.chapters.writing" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="角色" :value="data.characters" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="总字数" :value="data.word_total" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard class="stat-card" size="small">
            <NStatistic label="章·合计" :value="data.chapters.total" />
          </NCard>
        </NGridItem>
      </NGrid>

      <!-- 灵感各状态计数 -->
      <NCard class="section-card" size="small" style="margin-bottom:20px">
        <template #header><span class="section-title">灵感池状态</span></template>
        <NSpace>
          <NTag v-for="it in inspItems(data)" :key="it.key" :type="it.type" size="medium" round>
            {{ it.label }} · {{ it.n }}
          </NTag>
        </NSpace>
      </NCard>

      <!-- 卷列表 -->
      <NCard class="section-card" size="small" style="margin-bottom:20px">
        <template #header><span class="section-title">卷列表</span></template>
        <NEmpty v-if="!data.volume_list.length" description="无卷" />
        <div v-else class="vol-list">
          <div v-for="v in data.volume_list" :key="v.id" class="vol-row vol-row-edit">
            <div class="vol-line">
              <!-- 卷名内联编辑 -->
              <NInput
                v-if="volNameEditing[v.id]"
                v-model:value="volNameDraft[v.id]"
                size="small"
                style="width:180px"
                @keyup.enter="saveVolName(v)"
                @keyup.esc="cancelVolName(v)"
              />
              <template v-else>
                <span class="vol-name">{{ v.name || ('卷' + v.number) }}</span>
                <NButton size="tiny" quaternary class="vol-edit-btn" @click="startVolName(v)">编辑名</NButton>
              </template>
              <template v-if="volNameEditing[v.id]">
                <NButton size="tiny" type="primary" @click="saveVolName(v)">保存</NButton>
                <NButton size="tiny" @click="cancelVolName(v)">取消</NButton>
              </template>
              <NTag size="small" type="info" :bordered="false">{{ v.volume_type }}</NTag>
              <span class="vol-meta">{{ v.chapter_count }} 章</span>
              <NTag size="small" :type="volStatusType(v.status)" :bordered="false">{{ v.status }}</NTag>
            </div>
            <!-- theme_seeds 内联编辑 -->
            <div class="vol-seeds">
              <span class="vol-seeds-label">theme_seeds：</span>
              <NDynamicTags
                :value="v.theme_seeds || []"
                size="small"
                :max="50"
                @update:value="(s: string[]) => onSeedsChange(v, s)"
              />
            </div>
          </div>
        </div>
      </NCard>

      <!-- 角色快照 -->
      <NCard class="section-card" size="small" style="margin-bottom:20px">
        <template #header><span class="section-title">角色快照（点击进入角色页）</span></template>
        <NEmpty v-if="!data.character_snapshot.length" description="无角色" />
        <NGrid v-else :cols="'1 600:2 900:3'" :x-gap="12" :y-gap="12">
          <NGridItem v-for="c in data.character_snapshot" :key="c.id">
            <NCard class="char-card" size="small" hoverable @click="goCharacters">
              <div class="char-head">
                <span class="char-name">{{ c.name }}</span>
                <NTag size="small" :type="roleTagType(c.role)" :bordered="false">{{ c.role }}</NTag>
              </div>
              <div class="char-meta">
                <NTag size="tiny" :bordered="false">{{ c.state }}</NTag>
                <span v-if="c.pronoun" class="char-pronoun">代词：{{ c.pronoun }}</span>
              </div>
              <p v-if="c.personality_excerpt" class="char-excerpt">{{ c.personality_excerpt }}</p>
            </NCard>
          </NGridItem>
        </NGrid>
      </NCard>

      <!-- 世界观（内联编辑，WorldbookInline 三组） -->
      <NCard class="section-card" size="small">
        <template #header><span class="section-title">世界观</span></template>
        <WorldbookInline :wid="props.wid" :worldbook="data.worldbook" @updated="load" />
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.stat-card,
.section-card,
.char-card {
  background: #1a1d24;
  border: 1px solid #2a2f3a;
}
:deep(.stat-card .n-statistic .n-statistic-value__content),
:deep(.stat-card .n-statistic .n-statistic__label) {
  color: #e6e9ef;
}
:deep(.stat-card .n-statistic .n-statistic__label) {
  color: #7c8494;
}
.section-title {
  color: #e6e9ef;
  font-weight: 600;
}
:deep(.section-card .n-card-header__main) {
  color: #e6e9ef;
}
.vol-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vol-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: #15171c;
  border-radius: 4px;
}
.vol-row-edit {
  flex-direction: column;
  align-items: stretch;
}
.vol-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.vol-seeds {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.vol-seeds-label {
  color: #7c8494;
  font-size: 12px;
  flex: 0 0 auto;
}
.vol-edit-btn {
  color: #4ec9b0;
}
.vol-name {
  color: #e6e9ef;
  font-weight: 600;
  min-width: 60px;
}
.vol-meta {
  color: #7c8494;
  font-size: 12px;
}
.char-card {
  cursor: pointer;
  transition: border-color 0.15s;
}
.char-card:hover {
  border-color: #4ec9b0;
}
.char-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.char-name {
  color: #4ec9b0;
  font-weight: 600;
}
.char-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.char-pronoun {
  color: #7c8494;
  font-size: 12px;
}
.char-excerpt {
  margin: 4px 0 0;
  color: #7c8494;
  font-size: 13px;
  line-height: 1.5;
}
</style>
