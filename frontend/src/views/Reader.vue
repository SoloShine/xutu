<!-- src/views/Reader.vue -->
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { NSpin, NEmpty, NButton, NCollapse, NCollapseItem } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()

interface ChapterMeta {
  global_number: number
  title: string
  volume_id: number
  volume_name: string
  status: string
}
interface Paragraph {
  seq: number
  text: string
}
interface ChapterText {
  chapter: { global_number: number; title: string }
  paragraphs: Paragraph[]
}

const chapters = ref<ChapterMeta[]>([])
// 按 volume_name -> 该卷章节列表（按 chapters 全局序）
const grouped = ref<Array<{ volume_name: string; items: ChapterMeta[] }>>([])
const expanded = ref<string[]>([])

const selectedGnum = ref<number | null>(null)
const text = ref<ChapterText | null>(null)
const loadingList = ref(true)
const loadingText = ref(false)
const error = ref('')

// flat 全局序（用于首/末章禁用判断）
const flat = computed(() => chapters.value)
const firstGnum = computed(() => (flat.value.length ? flat.value[0].global_number : null))
const lastGnum = computed(() => (flat.value.length ? flat.value[flat.value.length - 1].global_number : null))
const isFirst = computed(() => selectedGnum.value === firstGnum.value)
const isLast = computed(() => selectedGnum.value === lastGnum.value)

const currentTitle = computed(() => text.value?.chapter?.title || '')

async function loadList() {
  if (!props.wid) { loadingList.value = false; return }
  loadingList.value = true
  error.value = ''
  try {
    const list = (await api.chapters(props.wid)) as ChapterMeta[]
    chapters.value = list
    // 分组：保持全局序，按 volume_name 聚合相邻
    const order: string[] = []
    const map = new Map<string, ChapterMeta[]>()
    for (const c of list) {
      if (!map.has(c.volume_name)) { map.set(c.volume_name, []); order.push(c.volume_name) }
      map.get(c.volume_name)!.push(c)
    }
    grouped.value = order.map((vn) => ({ volume_name: vn, items: map.get(vn)! }))
    expanded.value = order.slice() // 默认全展开
    // 默认选第一章
    if (list.length && selectedGnum.value === null) {
      selectedGnum.value = list[0].global_number
    }
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loadingList.value = false
  }
}

async function loadText(gnum: number) {
  if (!props.wid || gnum == null) return
  loadingText.value = true
  error.value = ''
  text.value = null
  try {
    text.value = (await api.chapterText(props.wid, gnum)) as ChapterText
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loadingText.value = false
  }
}

function selectChapter(gnum: number) {
  if (gnum === selectedGnum.value) return
  selectedGnum.value = gnum
}

function prevChapter() {
  if (selectedGnum.value === null) return
  const idx = flat.value.findIndex((c) => c.global_number === selectedGnum.value)
  if (idx > 0) selectedGnum.value = flat.value[idx - 1].global_number
}
function nextChapter() {
  if (selectedGnum.value === null) return
  const idx = flat.value.findIndex((c) => c.global_number === selectedGnum.value)
  if (idx >= 0 && idx < flat.value.length - 1) selectedGnum.value = flat.value[idx + 1].global_number
}

onMounted(loadList)
watch(() => props.wid, () => { selectedGnum.value = null; loadList() })
watch(selectedGnum, (g) => { if (g !== null) loadText(g) })
</script>

<template>
  <div class="reader-root">
    <!-- 左侧目录 -->
    <aside class="reader-toc">
      <div v-if="loadingList" class="toc-loading"><NSpin size="small" /></div>
      <template v-else-if="grouped.length">
        <NCollapse v-model:expanded-names="expanded" arrow-placement="left" display-directive="show">
          <NCollapseItem
            v-for="grp in grouped"
            :key="grp.volume_name"
            :name="grp.volume_name"
            :title="grp.volume_name"
          >
            <ul class="toc-list">
              <li
                v-for="ch in grp.items"
                :key="ch.global_number"
                :class="['toc-item', { active: ch.global_number === selectedGnum }]"
                @click="selectChapter(ch.global_number)"
              >
                <span class="toc-num">{{ ch.global_number }}</span>
                <span class="toc-title">{{ ch.title }}</span>
              </li>
            </ul>
          </NCollapseItem>
        </NCollapse>
      </template>
      <NEmpty v-else description="暂无章节" style="margin-top:40px" />
    </aside>

    <!-- 右侧主区 -->
    <main class="reader-main">
      <div v-if="loadingText" class="main-loading"><NSpin /></div>
      <div v-else-if="error" class="main-error">{{ error }}</div>
      <div v-else-if="!text" class="main-empty"><NEmpty description="请选择章节" /></div>
      <article v-else class="prose">
        <h1 class="chapter-title">{{ currentTitle }}</h1>
        <template v-if="text.paragraphs && text.paragraphs.length">
          <p
            v-for="p in [...text.paragraphs].sort((a, b) => a.seq - b.seq)"
            :key="p.seq"
            class="paragraph"
          >{{ p.text }}</p>
        </template>
        <div v-else class="no-text">本章暂无正文</div>
      </article>

      <!-- 底部导航 -->
      <div class="reader-nav" v-if="flat.length">
        <NButton :disabled="isFirst" @click="prevChapter">上一章</NButton>
        <span class="nav-pos" v-if="selectedGnum !== null">{{ selectedGnum }} / {{ lastGnum }}</span>
        <NButton :disabled="isLast" @click="nextChapter">下一章</NButton>
      </div>
    </main>
  </div>
</template>

<style scoped>
.reader-root {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 0;
}
.reader-toc {
  flex: 0 0 260px;
  overflow-y: auto;
  padding: 12px 8px;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}
.toc-loading { padding: 16px; }
.toc-list { list-style: none; margin: 0; padding: 0; }
.toc-item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: #b8bdc9;
  font-size: 13px;
  transition: background 0.15s;
}
.toc-item:hover { background: rgba(255, 255, 255, 0.05); }
.toc-item.active {
  background: rgba(0, 200, 200, 0.12);
  color: #00e5e5;
}
.toc-num { flex: 0 0 auto; opacity: 0.6; font-variant-numeric: tabular-nums; }
.toc-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.reader-main {
  flex: 1 1 auto;
  min-width: 0;
  overflow-y: auto;
  padding: 24px 16px 64px;
  display: flex;
  flex-direction: column;
}
.main-loading, .main-empty { display: flex; justify-content: center; padding-top: 80px; }
.main-error { color: #ff6b6b; padding: 24px; text-align: center; }

.prose {
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}
.chapter-title {
  color: #e6e9ef;
  font-size: 26px;
  font-weight: 600;
  margin: 8px 0 28px;
  text-align: center;
  line-height: 1.4;
}
.paragraph {
  color: #d8dce6;
  font-size: 16px;
  line-height: 1.9;
  text-indent: 2em;
  margin: 0 0 14px;
}
.no-text {
  color: #8a8f9c;
  text-align: center;
  padding: 60px 0;
}

.reader-nav {
  max-width: 720px;
  margin: 40px auto 0;
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.nav-pos { color: #8a8f9c; font-size: 13px; font-variant-numeric: tabular-nums; }
</style>
