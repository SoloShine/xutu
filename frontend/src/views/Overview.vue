<!-- src/views/Overview.vue -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NSpin, NGrid, NGridItem, NStatistic, NCard, NTag, NCollapse, NCollapseItem, NEmpty, NSpace,
} from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const router = useRouter()

interface Overview {
  name?: string
  volumes: number
  chapters: { completed: number; writing: number; total: number }
  characters: number
  word_total: number
  inspirations: { raw: number; refined: number; consumed: number; partial: number; discarded: number }
  volume_list: Array<{ id: number; number: number; name: string; volume_type: string; status: string; chapter_count: number }>
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

function goCharacters() { router.push(`/works/${props.wid}/characters`) }
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
          <div v-for="v in data.volume_list" :key="v.id" class="vol-row">
            <span class="vol-name">{{ v.name || ('卷' + v.number) }}</span>
            <NTag size="small" type="info" :bordered="false">{{ v.volume_type }}</NTag>
            <span class="vol-meta">{{ v.chapter_count }} 章</span>
            <NTag size="small" :type="volStatusType(v.status)" :bordered="false">{{ v.status }}</NTag>
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

      <!-- 世界观（只读，折叠分组） -->
      <NCard class="section-card" size="small">
        <template #header><span class="section-title">世界观</span></template>
        <NCollapse :default-expanded-names="['locations','themes','motifs']">
          <NCollapseItem title="地点 / Locations" name="locations">
            <NEmpty v-if="!data.worldbook.locations.length" description="无地点" />
            <div v-else class="wb-list">
              <div v-for="loc in data.worldbook.locations" :key="loc.id" class="wb-row">
                <div class="wb-row-head">
                  <span class="wb-name">{{ loc.name }}</span>
                  <NTag v-if="loc.loc_type" size="tiny" type="info" :bordered="false">{{ loc.loc_type }}</NTag>
                  <NTag v-if="loc.state" size="tiny" :bordered="false">{{ loc.state }}</NTag>
                </div>
                <p v-if="loc.description" class="wb-desc">{{ loc.description }}</p>
              </div>
            </div>
          </NCollapseItem>

          <NCollapseItem title="主题 / Themes" name="themes">
            <NEmpty v-if="!data.worldbook.themes.length" description="无主题" />
            <div v-else class="wb-list">
              <div v-for="th in data.worldbook.themes" :key="th.name" class="wb-row">
                <div class="wb-row-head">
                  <span class="wb-name">{{ th.name }}</span>
                </div>
                <p v-if="th.description" class="wb-desc">{{ th.description }}</p>
                <p v-if="th.evolution" class="wb-evol">演进：{{ th.evolution }}</p>
              </div>
            </div>
          </NCollapseItem>

          <NCollapseItem title="母题 / Motifs" name="motifs">
            <NEmpty v-if="!data.worldbook.motifs.length" description="无母题" />
            <div v-else class="wb-list">
              <div v-for="mo in data.worldbook.motifs" :key="mo.name" class="wb-row">
                <div class="wb-row-head">
                  <span class="wb-name">{{ mo.name }}</span>
                </div>
                <p v-if="mo.meaning" class="wb-desc">{{ mo.meaning }}</p>
                <p v-if="mo.evolution" class="wb-evol">演进：{{ mo.evolution }}</p>
              </div>
            </div>
          </NCollapseItem>
        </NCollapse>
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
.vol-list,
.wb-list {
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
.wb-row {
  padding: 8px 10px;
  background: #15171c;
  border-radius: 4px;
}
.wb-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wb-name {
  color: #e6e9ef;
  font-weight: 600;
}
.wb-desc {
  margin: 4px 0 0;
  color: #b8bfd0;
  font-size: 13px;
  line-height: 1.6;
}
.wb-evol {
  margin: 2px 0 0;
  color: #7c8494;
  font-size: 12px;
}
</style>
