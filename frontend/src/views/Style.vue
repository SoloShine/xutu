<!-- src/views/Style.vue -->
<!-- 文风配置:统计指纹(9维,只读参考) + 定性指令 + 4可编辑标量目标 + 预设 + 旋钮。
     scope:作品级(基线) / 卷级(覆盖,空字段继承作品级)。章级不存配置。 -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import {
  NSpin, NEmpty, NCard, NTag, NProgress, NSpace, NAlert, NInput,
  NInputNumber, NButton, NTooltip, NRadioGroup, NRadioButton, NSelect, useMessage,
} from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()

interface DimDef { label: string; unit: string; formula: string; interpret: string }
interface Fingerprint { _scope?: string; _volume_id?: number; _source_work?: string; _directive?: string; _scalar_targets?: Record<string, number>; [k: string]: any }
const configs = ref<Fingerprint[]>([])
const dimDefs = ref<Record<string, DimDef>>({})
const volumes = ref<{ id: number; name: string }[]>([])
const actual = ref<{ fingerprint: Fingerprint | null; scalars: Record<string, number> | null; chapter_count: number; paragraph_count: number } | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')

// 编辑态
const scope = ref<'work' | 'volume'>('work')
const volumeId = ref<number | null>(null)
const directive = ref('')
const wcMin = ref(3000), wcMax = ref(5000), maxRounds = ref(3)
// 4 标量目标(% 或 /千字);空=继承指纹派生
const tDash = ref<number|null>(null), tNotx = ref<number|null>(null), tDlg = ref<number|null>(null), tRhet = ref<number|null>(null)

const workCfg = computed(() => configs.value.find(c => c._scope === 'work') || null)
const curCfg = computed(() => scope.value === 'volume'
  ? configs.value.find(c => c._scope === 'volume' && c._volume_id === volumeId.value) || null
  : workCfg.value)

// 指纹派生的标量(作 placeholder/默认)
const derived = computed(() => {
  const fp = workCfg.value || {}
  return {
    dash: fp.dash ? Math.round((1 - (fp.dash['0'] || 0)) * 1000) / 10 : null,
    notx: fp.structure ? Math.round((fp.structure.notXisY || 0) * 1000) / 10 : null,
    dlg: fp.dialogue_ratio ? Math.round((fp.dialogue_ratio.value || 0) * 1000) / 10 : null,
    rhet: fp.rhetoric ? fp.rhetoric.value : null,
  }
})

// 当前有效目标标量(显式 scalar_targets 覆盖指纹派生)
const targetScalars = computed(() => {
  const st = workCfg.value?._scalar_targets || {}
  const d = derived.value
  return {
    dash: st.dash_rate != null ? st.dash_rate * 100 : d.dash,
    notx: st.notXisY_rate != null ? st.notXisY_rate * 100 : d.notx,
    dlg: st.dialogue_ratio != null ? st.dialogue_ratio * 100 : d.dlg,
    rhet: st.rhetoric_per_k != null ? st.rhetoric_per_k : d.rhet,
  }
})

// 实测 vs 目标(4 标量),用于对比卡
const scalarCompare = computed(() => {
  const sc = actual.value?.scalars
  if (!sc) return null
  const tg = targetScalars.value
  const row = (label: string, unit: string, a: number, t: number | null) => ({
    label, unit, actual: Math.round(a * 10) / 10, target: t != null ? Math.round(t * 10) / 10 : null,
    over: t != null && a > t * 1.5 + 0.01,  // 明显超标
  })
  return [
    row('破折号率', '%', (sc.dash_rate || 0) * 100, tg.dash),
    row('「不是A是B」率', '%', (sc.notXisY_rate || 0) * 100, tg.notx),
    row('对白占比', '%', (sc.dialogue_ratio || 0) * 100, tg.dlg),
    row('修辞密度', '/千字', sc.rhetoric_per_k || 0, tg.rhet),
  ]
})

function populateFrom(c: Fingerprint | null) {
  directive.value = c?._directive || ''
  const st = c?._scalar_targets || {}
  tDash.value = st.dash_rate != null ? Math.round(st.dash_rate * 1000) / 10 : null
  tNotx.value = st.notXisY_rate != null ? Math.round(st.notXisY_rate * 1000) / 10 : null
  tDlg.value = st.dialogue_ratio != null ? Math.round(st.dialogue_ratio * 1000) / 10 : null
  tRhet.value = st.rhetoric_per_k != null ? st.rhetoric_per_k : null
}

async function load() {
  if (!props.wid) return
  loading.value = true; error.value = ''
  try {
    const [sr, ov, ac] = await Promise.all([
      api.style(props.wid), api.overview(props.wid) as any,
      api.styleActual(props.wid) as any,
    ])
    configs.value = sr.configs || []
    dimDefs.value = sr.dim_definitions || {}
    actual.value = ac
    volumes.value = (ov.volume_list || []).map((v: any) => ({ id: v.id, name: v.name }))
    if (volumes.value.length && volumeId.value == null) volumeId.value = volumes.value[0].id
    populateFrom(curCfg.value)
  } catch (e: any) { error.value = e.message || String(e) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })
watch([scope, volumeId], () => populateFrom(curCfg.value))

const dirty = computed(() => {
  const c = curCfg.value
  if (!c) return true
  const st = c._scalar_targets || {}
  return directive.value !== (c._directive || '')
    || scalarsPayload().dash_rate !== st.dash_rate
    || scalarsPayload().notXisY_rate !== st.notXisY_rate
    || scalarsPayload().dialogue_ratio !== st.dialogue_ratio
    || scalarsPayload().rhetoric_per_k !== st.rhetoric_per_k
})
function scalarsPayload() {
  const o: Record<string, number> = {}
  if (tDash.value != null) o.dash_rate = tDash.value / 100
  if (tNotx.value != null) o.notXisY_rate = tNotx.value / 100
  if (tDlg.value != null) o.dialogue_ratio = tDlg.value / 100
  if (tRhet.value != null) o.rhetoric_per_k = tRhet.value
  return o
}

// 预设:一组标量目标快捷设定
function applyPreset(name: string) {
  if (name === '冷硬快节奏') { tDash.value = 2; tNotx.value = 0.2; tDlg.value = 25; tRhet.value = 2 }
  else if (name === '平稳叙事') { tDash.value = 4; tNotx.value = 0.5; tDlg.value = 15; tRhet.value = 3 }
  else if (name === '浓修辞') { tDash.value = 5; tNotx.value = 0.5; tDlg.value = 20; tRhet.value = 8 }
  msg.info(`已套用预设「${name}」,点保存生效`)
}

async function save() {
  saving.value = true
  try {
    await api.setStyle(props.wid, {
      scope: scope.value,
      volume_id: scope.value === 'volume' ? volumeId.value : undefined,
      directive: directive.value,
      word_count_target: scope.value === 'work' ? [wcMin.value, wcMax.value] : undefined,
      max_edit_rounds: scope.value === 'work' ? maxRounds.value : undefined,
      scalar_targets: scalarsPayload(),
    })
    msg.success(`${scope.value === 'volume' ? '卷级' : '作品级'}文风配置已保存`)
    await load()
  } catch (e: any) { msg.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

const DIMS = ['sentence_length', 'paragraph_length', 'period', 'dialogue', 'dialogue_ratio',
  'dash', 'rhetoric', 'structure', 'sensory']
function pct(n: number) { return Math.round((n || 0) * 1000) / 10 }
function entries(fp: Fingerprint, key: string): [string, number][] {
  const d = fp[key]; if (!d || typeof d !== 'object') return []
  return Object.entries(d).filter(([k]) => !k.startsWith('_')) as [string, number][]
}
function defOf(key: string) { return dimDefs.value[key] }
</script>

<template>
  <div class="style-view">
    <NSpin :show="loading">
      <div v-if="error" style="color: var(--n-error-color)">{{ error }}</div>

      <NEmpty v-else-if="!configs.length && !volumes.length" description="该作品无文风配置">
        <template #extra>
          <NAlert type="info" :bordered="false" style="text-align:left;max-width:540px">
            可先填"文风指令"定性描述(无需指纹即生效),或灌对标指纹:
            <pre style="margin:6px 0 0;font-size:12px">python scripts/extract_reference_style.py \
  --txt "参考作品.txt" --project projects/{{ props.wid }} --scope work</pre>
          </NAlert>
        </template>
      </NEmpty>

      <NSpace v-else vertical :size="12">
        <!-- scope 选择 + 编辑区 -->
        <NCard size="small" title="文风配置(可编辑)">
          <NSpace align="center" :size="10" style="margin-bottom:10px">
            <NRadioGroup v-model:value="scope" size="small">
              <NRadioButton value="work">作品级(基线)</NRadioButton>
              <NRadioButton value="volume">卷级(覆盖)</NRadioButton>
            </NRadioGroup>
            <NSelect v-if="scope === 'volume'" v-model:value="volumeId" size="small"
              :options="volumes.map(v => ({ label: v.name, value: v.id }))" style="width:160px" />
            <NTag v-if="scope === 'volume'" size="small" type="warning" round>空字段=继承作品级</NTag>
            <NTag v-else size="small" type="info" round>全作品生效</NTag>
          </NSpace>

          <NAlert v-if="scope === 'volume' && !curCfg" type="default" :bordered="false" style="margin-bottom:8px">
            该卷尚未设覆盖,保存后将创建卷级配置(只存你填的字段,其余继承作品级)。
          </NAlert>

          <!-- 文风指令 -->
          <div class="field-label">文风指令(定性,注入 writer)</div>
          <NInput v-model:value="directive" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
            :placeholder="scope === 'volume' ? '留空=继承作品级指令' : '短促冷硬、镜头式白描、不用心理独白...'" />

          <!-- 4 标量目标(可编辑,空=指纹派生) -->
          <div class="field-label" style="margin-top:10px">
            标量目标(style-check 比对;留空=用指纹派生值)
          </div>
          <div class="scalar-grid">
            <div class="scalar"><span>破折号率(%)</span><NInputNumber v-model:value="tDash" :min="0" :max="100" :step="1" size="small" :placeholder="derived.dash != null ? String(derived.dash) : ''" /></div>
            <div class="scalar"><span>「不是A是B」率(%)</span><NInputNumber v-model:value="tNotx" :min="0" :max="100" :step="0.1" size="small" :placeholder="derived.notx != null ? String(derived.notx) : ''" /></div>
            <div class="scalar"><span>对白占比(%)</span><NInputNumber v-model:value="tDlg" :min="0" :max="100" :step="1" size="small" :placeholder="derived.dlg != null ? String(derived.dlg) : ''" /></div>
            <div class="scalar"><span>修辞(/千字)</span><NInputNumber v-model:value="tRhet" :min="0" :step="0.5" size="small" :placeholder="derived.rhet != null ? String(derived.rhet) : ''" /></div>
          </div>
          <NSpace :size="6" style="margin-top:6px">
            <NButton size="tiny" quaternary @click="applyPreset('冷硬快节奏')">冷硬快节奏</NButton>
            <NButton size="tiny" quaternary @click="applyPreset('平稳叙事')">平稳叙事</NButton>
            <NButton size="tiny" quaternary @click="applyPreset('浓修辞')">浓修辞</NButton>
          </NSpace>

          <!-- 旋钮(仅作品级;卷级继承) -->
          <template v-if="scope === 'work'">
            <div class="field-label" style="margin-top:10px">旋钮</div>
            <NSpace :size="10" align="center">
              <span class="knob-label">字数</span>
              <NInputNumber v-model:value="wcMin" :min="500" :step="500" size="small" style="width:110px" />
              <span>~</span>
              <NInputNumber v-model:value="wcMax" :min="500" :step="500" size="small" style="width:110px" />
              <span class="knob-label" style="margin-left:12px">编辑轮</span>
              <NInputNumber v-model:value="maxRounds" :min="0" :max="6" size="small" style="width:80px" />
            </NSpace>
          </template>

          <div style="margin-top:12px">
            <NButton type="primary" size="small" :loading="saving" :disabled="!dirty" @click="save">保存</NButton>
          </div>
        </NCard>

        <!-- 当前实测 vs 目标(live extract 已写章节) -->
        <NCard v-if="actual" size="small" title="当前实测 vs 目标(live)">
          <template #header-extra>
            <NTag size="small" round>{{ actual.chapter_count }}章 / {{ actual.paragraph_count }}段(已写)</NTag>
          </template>
          <NAlert v-if="!actual.fingerprint" type="default" :bordered="false">尚无已写章节,无法实测。</NAlert>
          <template v-else>
            <div class="field-label">标量对比(实测 = 弹着点 / 目标 = 靶)</div>
            <div class="cmp-table">
              <div v-for="r in scalarCompare" :key="r.label" class="cmp-row" :class="{ over: r.over }">
                <span class="cmp-label">{{ r.label }}</span>
                <div class="cmp-bars">
                  <div class="cmp-line"><span class="cmp-tag actual">实测</span>
                    <NProgress type="line" :percentage="Math.min(r.unit==='%'?r.actual:r.actual*5,100)" :height="10" :show-indicator="false" :status="r.over?'warning':'success'" style="flex:1" />
                    <span class="cmp-val">{{ r.actual }}{{ r.unit }}</span></div>
                  <div class="cmp-line"><span class="cmp-tag target">目标</span>
                    <NProgress type="line" :percentage="r.target!=null?Math.min(r.unit==='%'?r.target:r.target*5,100):0" :height="10" :show-indicator="false" color="#999" style="flex:1" />
                    <span class="cmp-val">{{ r.target!=null?r.target:'—' }}{{ r.unit }}</span></div>
                </div>
              </div>
            </div>
            <div class="field-label" style="margin-top:10px">实测 9 维分布</div>
            <div class="dim-grid">
              <div v-for="dim in DIMS" :key="dim" class="dim">
                <div class="dim-head"><span class="dim-label">{{ defOf(dim)?.label || dim }}</span></div>
                <div v-if="actual.fingerprint[dim]?.value !== undefined" class="single-val">
                  {{ dim === 'dialogue_ratio' ? Math.round(actual.fingerprint[dim].value*1000)/10 + '%' : actual.fingerprint[dim].value + ' /千字' }}
                </div>
                <div v-else>
                  <div v-for="[k, v] in entries(actual.fingerprint, dim)" :key="k" class="bar-row">
                    <span class="bar-k">{{ k }}</span>
                    <NProgress type="line" :percentage="pct(v)" :height="9" :show-indicator="false" style="flex:1" />
                    <span class="bar-v">{{ pct(v) }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </NCard>

        <!-- 统计指纹(只读参考) -->
        <NCard v-if="workCfg" size="small" title="统计指纹 · 只读参考(来自 extract)">
          <template #header-extra>
            <NTag v-if="workCfg._source_work" size="small" type="info" round>{{ workCfg._source_work }}</NTag>
          </template>
          <div class="dim-grid">
            <div v-for="dim in DIMS" :key="dim" class="dim">
              <div class="dim-head">
                <NTooltip trigger="hover" placement="top">
                  <template #trigger><span class="dim-label">{{ defOf(dim)?.label || dim }} ℹ</span></template>
                  <div style="max-width:280px">
                    <div><b>{{ defOf(dim)?.label }}</b> ({{ defOf(dim)?.unit }})</div>
                    <div style="opacity:.8">{{ defOf(dim)?.formula }}</div>
                    <div style="opacity:.65;margin-top:4px">{{ defOf(dim)?.interpret }}</div>
                  </div>
                </NTooltip>
              </div>
              <div v-if="workCfg[dim]?.value !== undefined" class="single-val">
                {{ dim === 'dialogue_ratio' ? Math.round(workCfg[dim].value*1000)/10 + '%' : workCfg[dim].value + ' /千字' }}
              </div>
              <div v-else>
                <div v-for="[k, v] in entries(workCfg, dim)" :key="k" class="bar-row">
                  <span class="bar-k" :class="{ hi: dim === 'structure' && k === 'notXisY' }">{{ k }}</span>
                  <NProgress type="line" :percentage="pct(v)" :height="10" :show-indicator="false"
                    :status="(dim === 'structure' && k === 'notXisY' && pct(v) > 2) ? 'warning' : 'success'" style="flex:1" />
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
.field-label { font-size: 12px; opacity: 0.65; margin-bottom: 4px; }
.knob-label { font-size: 13px; opacity: 0.7; }
.scalar-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.scalar { display: flex; flex-direction: column; gap: 2px; }
.scalar span { font-size: 11px; opacity: 0.7; }
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
.dim { background: var(--n-color); border: 1px solid var(--n-border-color); border-radius: 8px; padding: 10px; }
.dim-label { font-weight: 600; cursor: help; border-bottom: 1px dotted; }
.single-val { font-size: 20px; font-weight: 700; color: var(--n-primary-color); padding: 4px 0; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; font-size: 12px; }
.bar-k { min-width: 56px; opacity: 0.8; }
.bar-k.hi { color: var(--n-warning-color); font-weight: 700; }
.bar-v { min-width: 42px; text-align: right; font-variant-numeric: tabular-nums; }
.cmp-table { display: flex; flex-direction: column; gap: 8px; }
.cmp-row { display: flex; align-items: center; gap: 10px; }
.cmp-row.over .cmp-label { color: var(--n-warning-color); font-weight: 700; }
.cmp-label { min-width: 110px; font-size: 13px; }
.cmp-bars { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.cmp-line { display: flex; align-items: center; gap: 6px; }
.cmp-tag { font-size: 10px; min-width: 28px; opacity: 0.6; }
.cmp-tag.actual { color: var(--n-primary-color); opacity: 1; }
.cmp-val { min-width: 64px; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
</style>
