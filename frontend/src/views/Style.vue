<!-- src/views/Style.vue -->
<!-- 文风配置视图:统计指纹(9维) + 定性文风指令(可编辑,注入 writer) + 旋钮(字数/编辑轮/hygiene)。
     指纹管"分布",指令管"气质"。维度定义 tooltip 可解释化。 -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import {
  NSpin, NEmpty, NCard, NTag, NProgress, NSpace, NAlert, NInput,
  NInputNumber, NButton, NTooltip, useMessage,
} from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()

interface DimDef { label: string; unit: string; formula: string; interpret: string }
interface Fingerprint {
  _scope?: string; _volume_id?: number; _source_work?: string; _directive?: string
  [k: string]: any
}
const configs = ref<Fingerprint[]>([])
const dimDefs = ref<Record<string, DimDef>>({})
const loading = ref(true)
const saving = ref(false)
const error = ref('')

// 可编辑旋钮(作品级;存本地编辑态,保存时 POST)
const directive = ref('')
const wcMin = ref<number>(3000)
const wcMax = ref<number>(5000)
const maxRounds = ref<number>(3)
const dirty = computed(() => {
  const c = workCfg.value
  if (!c) return false
  return directive.value !== (c._directive || '')
    || wcMin.value !== (parseWC(c).min) || wcMax.value !== (parseWC(c).max)
    || maxRounds.value !== 3
})

const workCfg = computed(() => configs.value.find(c => c._scope === 'work') || configs.value[0] || null)
function parseWC(c: Fingerprint | null) {
  // word_count_target 不在 fingerprint 里,单独存——这里仅占位,实际从 configs 拓展字段读
  return { min: 3000, max: 5000 }
}

async function load() {
  if (!props.wid) return
  loading.value = true; error.value = ''
  try {
    const r = (await api.style(props.wid)) as any
    configs.value = r.configs || []
    dimDefs.value = r.dim_definitions || {}
    if (workCfg.value) {
      directive.value = workCfg.value._directive || ''
    }
  } catch (e: any) { error.value = e.message || String(e) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })

async function save() {
  saving.value = true
  try {
    await api.setStyle(props.wid, {
      scope: 'work',
      directive: directive.value,
      word_count_target: [wcMin.value, wcMax.value],
      max_edit_rounds: maxRounds.value,
    })
    msg.success('文风配置已保存(后续写/润色生效)')
    await load()
  } catch (e: any) { msg.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

const DIMS = ['sentence_length', 'paragraph_length', 'period', 'dialogue', 'dialogue_ratio',
  'dash', 'rhetoric', 'structure', 'sensory']
function pct(n: number) { return Math.round((n || 0) * 1000) / 10 }
function entries(fp: Fingerprint, key: string): [string, number][] {
  const d = fp[key]
  if (!d || typeof d !== 'object') return []
  return Object.entries(d).filter(([k]) => !k.startsWith('_')) as [string, number][]
}
function defOf(key: string): DimDef | undefined { return dimDefs.value[key] }
const notXisY = computed(() => workCfg.value?.structure?.notXisY)
const dash0 = computed(() => workCfg.value?.dash?.['0'])
const dlgRatio = computed(() => workCfg.value?.dialogue_ratio?.value)
const rhetoric = computed(() => workCfg.value?.rhetoric?.value)
</script>

<template>
  <div class="style-view">
    <NSpin :show="loading">
      <div v-if="error" style="color: var(--n-error-color)">{{ error }}</div>

      <NEmpty v-else-if="!configs.length" description="该作品尚无文风指纹/配置">
        <template #extra>
          <NAlert type="info" :bordered="false" style="text-align: left; max-width: 540px">
            无指纹时 Polish 跳过、旋钮走代码默认。<br>
            注入对标指纹:<pre style="margin:6px 0 0;font-size:12px">python scripts/extract_reference_style.py \
  --txt "参考作品.txt" --project projects/{{ props.wid }} --scope work</pre>
            下方仍可填"文风指令"定性描述(无需指纹即可生效)。
          </NAlert>
        </template>
      </NEmpty>

      <NSpace v-else vertical :size="12">
        <NAlert v-if="notXisY !== undefined" type="success" :bordered="false">
          对标基准:notXisY ≈ {{ pct(notXisY!) }}%、无破折号段落 {{ pct(dash0!) }}%、
          对白占比 {{ Math.round((dlgRatio||0)*100) }}%、修辞 {{ rhetoric||0 }}/千字
        </NAlert>

        <!-- 定性文风指令(可编辑,核心新增) -->
        <NCard size="small" title="文风指令 · 定性要求(注入 writer,高于统计指纹)">
          <NInput
            v-model:value="directive"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="用自然语言描述想要的文风气质,如:短促冷硬、镜头式白描、不用心理独白、对白简省、环境留白、克制感官。这段会作为系统级指令注入每章 ChapterWriter。"
          />
          <NSpace :size="10" align="center" style="margin-top: 8px">
            <span class="knob-label">字数目标</span>
            <NInputNumber v-model:value="wcMin" :min="500" :step="500" size="small" style="width:110px" />
            <span>~</span>
            <NInputNumber v-model:value="wcMax" :min="500" :step="500" size="small" style="width:110px" />
            <span class="knob-label" style="margin-left:12px">最大编辑轮</span>
            <NInputNumber v-model:value="maxRounds" :min="0" :max="6" size="small" style="width:80px" />
            <NButton type="primary" size="small" :loading="saving" :disabled="!dirty" @click="save">保存</NButton>
          </NSpace>
        </NCard>

        <!-- 统计指纹 9 维(带定义 tooltip) -->
        <NCard v-for="(fp, i) in configs" :key="i" size="small"
               :title="`统计指纹 · ${fp._scope === 'volume' ? '卷级' : '作品级'}`">
          <template #header-extra>
            <NSpace :size="6">
              <NTag size="small" round>{{ fp._scope }}</NTag>
              <NTag v-if="fp._source_work" size="small" type="info" round>{{ fp._source_work }}</NTag>
            </NSpace>
          </template>
          <div class="dim-grid">
            <div v-for="dim in DIMS" :key="dim" class="dim">
              <div class="dim-head">
                <NTooltip trigger="hover" placement="top">
                  <template #trigger>
                    <span class="dim-label">{{ defOf(dim)?.label || dim }} ℹ</span>
                  </template>
                  <div style="max-width: 280px">
                    <div><b>{{ defOf(dim)?.label }}</b> ({{ defOf(dim)?.unit }})</div>
                    <div style="opacity:.8">{{ defOf(dim)?.formula }}</div>
                    <div style="opacity:.65;margin-top:4px">{{ defOf(dim)?.interpret }}</div>
                  </div>
                </NTooltip>
              </div>
              <!-- 单值维度(dialogue_ratio/rhetoric) -->
              <div v-if="fp[dim]?.value !== undefined" class="single-val">
                {{ dim === 'dialogue_ratio' ? Math.round(fp[dim].value*1000)/10 + '%' : fp[dim].value + ' /千字' }}
              </div>
              <!-- 直方图维度 -->
              <div v-else>
                <div v-for="[k, v] in entries(fp, dim)" :key="k" class="bar-row">
                  <span class="bar-k" :class="{ hi: dim === 'structure' && k === 'notXisY' }">{{ k }}</span>
                  <NProgress type="line" :percentage="pct(v)" :height="10" :show-indicator="false"
                    :status="(dim === 'structure' && k === 'notXisY' && pct(v) > 2) ? 'warning' : 'success'"
                    style="flex: 1" />
                  <span class="bar-v">{{ pct(v) }}%</span>
                </div>
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
.knob-label { font-size: 13px; opacity: 0.7; }
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
.dim { background: var(--n-color); border: 1px solid var(--n-border-color); border-radius: 8px; padding: 10px; }
.dim-head { margin-bottom: 6px; }
.dim-label { font-weight: 600; cursor: help; border-bottom: 1px dotted; }
.single-val { font-size: 20px; font-weight: 700; color: var(--n-primary-color); padding: 4px 0; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; font-size: 12px; }
.bar-k { min-width: 56px; opacity: 0.8; }
.bar-k.hi { color: var(--n-warning-color); font-weight: 700; opacity: 1; }
.bar-v { min-width: 42px; text-align: right; font-variant-numeric: tabular-nums; }
</style>
