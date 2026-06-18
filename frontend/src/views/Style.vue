<!-- src/views/Style.vue -->
<!-- 文风指纹视图：展示对标参考作品提取的 7 维度分布（Polish 据此微调正文）。
     无指纹时提示如何注入（extract_reference_style.py / 向导）。 -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { NSpin, NEmpty, NCard, NTag, NProgress, NSpace, NAlert } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()

interface Fingerprint {
  _scope?: string
  _volume_id?: number
  _source_work?: string
  sentence_length?: Record<string, number>
  paragraph_length?: Record<string, number>
  dash?: Record<string, number>
  period?: Record<string, number>
  dialogue?: Record<string, number>
  structure?: Record<string, number>
  sensory?: Record<string, number>
}

const fps = ref<Fingerprint[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  if (!props.wid) return
  loading.value = true; error.value = ''
  try {
    fps.value = (await api.style(props.wid)) as any
  } catch (e: any) { error.value = e.message || String(e) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })

// 维度展示顺序 + 中文标签
const DIMS: { key: string; label: string; hint: string }[] = [
  { key: 'sentence_length', label: '句子长度', hint: '短句占比高=节奏快' },
  { key: 'paragraph_length', label: '段落长度', hint: '网文常一句一段' },
  { key: 'period', label: '句号密度', hint: '每段句号数' },
  { key: 'dialogue', label: '对白/叙述', hint: '纯叙述 vs 混合 vs 纯对话' },
  { key: 'dash', label: '破折号', hint: '参考好作品 96% 段落不用' },
  { key: 'structure', label: '句式', hint: 'notXisY=“不是A是B”应≈0' },
  { key: 'sensory', label: '感官', hint: '视觉/听觉/触觉分布' },
]

// 取某维度的 [桶名, 比例] 列表（类型安全,绕开 Vue 空对象迭代把方法键算进来的 TS 问题）
function entries(fp: Fingerprint, key: string): [string, number][] {
  const d = (fp as any)[key]
  if (!d || typeof d !== 'object') return []
  return Object.entries(d).filter(([k]) => !k.startsWith('_')) as [string, number][]
}

function pct(n: number) { return Math.round((n || 0) * 1000) / 10 }
function scopeLabel(fp: Fingerprint) {
  return fp._scope === 'volume' ? `卷级 (vol ${fp._volume_id})` : '作品级'
}
// 结构维度里把 notXisY 单独高亮
const notXisY = computed(() => {
  const fp = fps.value.find(f => f._scope === 'work') || fps.value[0]
  return fp?.structure?.notXisY
})
const dash0 = computed(() => {
  const fp = fps.value.find(f => f._scope === 'work') || fps.value[0]
  return fp?.dash?.['0']
})
</script>

<template>
  <div class="style-view">
    <NSpin :show="loading">
      <div v-if="error" style="color: var(--n-error-color)">{{ error }}</div>

      <NEmpty v-else-if="!fps.length" description="该作品尚无文风指纹">
        <template #extra>
          <NAlert type="info" :bordered="false" style="text-align: left; max-width: 520px">
            无指纹时 Polish 阶段会被跳过,正文无文风约束(易飘)。<br>
            注入方式:从对标参考作品提取——
            <pre style="margin: 6px 0 0; font-size: 12px">python scripts/extract_reference_style.py \
  --txt "参考作品.txt" --project projects/{{ props.wid }} --scope work</pre>
          </NAlert>
        </template>
      </NEmpty>

      <NSpace v-else vertical :size="12">
        <NAlert v-if="notXisY !== undefined && dash0 !== undefined" type="success" :bordered="false">
          对标基准:notXisY(“不是A是B”句式)≈ {{ pct(notXisY!) }}%、无破折号段落 {{ pct(dash0!) }}%
        </NAlert>

        <NCard v-for="(fp, i) in fps" :key="i" size="small" :title="`文风指纹 · ${scopeLabel(fp)}`">
          <template #header-extra>
            <NSpace :size="6">
              <NTag size="small" round>{{ fp._scope }}</NTag>
              <NTag v-if="fp._source_work" size="small" type="info" round>{{ fp._source_work }}</NTag>
            </NSpace>
          </template>

          <div class="dim-grid">
            <div v-for="dim in DIMS" :key="dim.key" class="dim">
              <div class="dim-head">
                <span class="dim-label">{{ dim.label }}</span>
                <span class="dim-hint">{{ dim.hint }}</span>
              </div>
              <div v-for="[k, v] in entries(fp, dim.key)" :key="k" class="bar-row">
                <span class="bar-k" :class="{ hi: dim.key === 'structure' && k === 'notXisY' }">{{ k }}</span>
                <NProgress
                  type="line"
                  :percentage="pct(v)"
                  :height="10"
                  :show-indicator="false"
                  :status="(dim.key === 'structure' && k === 'notXisY' && pct(v) > 2) ? 'warning' : 'success'"
                  style="flex: 1"
                />
                <span class="bar-v">{{ pct(v) }}%</span>
              </div>
            </div>
          </div>
        </NCard>
      </NSpace>
    </NSpin>
  </div>
</template>

<style scoped>
.style-view { padding: 12px; }
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.dim { background: var(--n-color); border: 1px solid var(--n-border-color); border-radius: 8px; padding: 10px; }
.dim-head { margin-bottom: 6px; }
.dim-label { font-weight: 600; margin-right: 8px; }
.dim-hint { font-size: 11px; opacity: 0.55; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; font-size: 12px; }
.bar-k { min-width: 56px; opacity: 0.8; }
.bar-k.hi { color: var(--n-warning-color); font-weight: 700; opacity: 1; }
.bar-v { min-width: 42px; text-align: right; font-variant-numeric: tabular-nums; }
</style>
