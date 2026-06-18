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
const importPath = ref('')
const importing = ref(false)
const rangeStart = ref<number|null>(null), rangeEnd = ref<number|null>(null)
// 文件选择 + 预览
const fileName = ref('')
const fileText = ref('')
const fileEnc = ref('UTF-8')
const preview = ref<{chapter_count:number;chunked:boolean;sample_titles:string[];total_chars:number}|null>(null)
const previewing = ref(false)

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

// 导入参考作品(本地 txt 路径,服务端纯程序提取)
// 文件选择 → 读正文(按编码)→ 预览切章信息(总章数/切片/样章),不存
function pickFile() { document.getElementById('style-file-input')?.click() }
function onFilePick(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0]
  if (!f) return
  fileName.value = f.name; fileText.value = ''; preview.value = null
  const reader = new FileReader()
  reader.onload = async () => {
    fileText.value = String(reader.result || '')
    previewing.value = true
    try {
      preview.value = await api.previewReference(props.wid, fileText.value) as any
      const n = preview.value?.chapter_count || 0
      if (n) { rangeStart.value = null; rangeEnd.value = null }
    } catch (e:any) { msg.error('预览失败: '+(e.message||e)) }
    finally { previewing.value = false }
  }
  reader.readAsText(f, fileEnc.value)
}

// 从已选文件提取(用 fileText;range 可选)
async function importRef() {
  const text = fileText.value
  if (!text) { msg.warning('先选择参考作品 txt 文件'); return }
  importing.value = true
  try {
    const range = (rangeStart.value != null && rangeEnd.value != null)
      ? [rangeStart.value, rangeEnd.value] : undefined
    const r: any = await api.importReference(props.wid, {
      text, scope: scope.value, source_work: fileName.value,
      volume_id: scope.value === 'volume' ? volumeId.value : undefined,
      chapter_range: range,
    })
    if (r && r.ok !== false) {
      const it = r.item || r
      msg.success(`已提取: ${it.chapter_count||'?'}章/抽样${it.sampled_chapters||'?'}${it.directive_seeded?'+指令':''}`)
      fileName.value=''; fileText.value=''; preview.value=null; rangeStart.value=null; rangeEnd.value=null
      const inp = document.getElementById('style-file-input') as HTMLInputElement
      if (inp) inp.value = ''
      await load()
    } else { msg.error('导入失败: '+((r&&r.error)||'未知')) }
  } catch (e:any) { msg.error('导入失败: '+(e.message||e)) }
  finally { importing.value = false }
}
function entries(fp: Fingerprint, key: string): [string, number][] {
  const d = fp[key]; if (!d || typeof d !== 'object') return []
  return Object.entries(d).filter(([k]) => !k.startsWith('_')) as [string, number][]
}
// 某 dim 各桶的目标+实测值(同 bucket 配对)
function dimRows(dim: string) {
  const t = (workCfg.value as any)?.[dim] || {}
  const a = (actual.value?.fingerprint as any)?.[dim] || {}
  return Object.keys(t).filter(k => !k.startsWith('_')).map(k => ({ k, target: t[k] || 0, actual: a[k] || 0 }))
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

          <!-- 导入参考作品(纯程序提取,零LLM) -->
          <div class="field-label">导入参考作品 → 提取指纹+派生指令</div>
          <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
            <input id="style-file-input" type="file" accept=".txt,.text" style="display:none" @change="onFilePick" />
            <NButton size="small" @click="pickFile">选择 txt 文件</NButton>
            <NTag v-if="fileName" size="small" type="info" round>{{ fileName }}</NTag>
            <span class="knob-label">编码</span>
            <NSelect v-model:value="fileEnc" size="small" :options="[{label:'UTF-8',value:'UTF-8'},{label:'GBK',value:'GBK'},{label:'GB18030',value:'GB18030'}]" style="width:110px" />
          </NSpace>
          <!-- 预览:总章数/是否切片/样章 -->
          <NAlert v-if="preview" :type="preview.chunked ? 'warning' : 'info'" :bordered="false" style="margin-bottom:8px">
            <b>{{ preview.chapter_count }}</b> 章 · {{ preview.total_chars }} 字
            <NTag v-if="preview.chunked" size="tiny" type="warning" round>非标准章名→按字数切片</NTag>
            <div style="opacity:.7;font-size:12px;margin-top:2px">样章: {{ preview.sample_titles.join(' / ') }}</div>
          </NAlert>
          <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
            <span class="knob-label">章范围(留空=中段动态抽样)</span>
            <NInputNumber v-model:value="rangeStart" :min="1" :max="preview?.chapter_count" size="small" :placeholder="preview?`1`:'起'" style="width:80px" />
            <span>~</span>
            <NInputNumber v-model:value="rangeEnd" :min="1" :max="preview?.chapter_count" size="small" :placeholder="preview?`${preview.chapter_count}`:'止'" style="width:80px" />
            <NButton size="small" type="primary" :loading="importing || previewing" :disabled="!fileText" @click="importRef">提取→{{ scope === 'volume' ? '卷级' : '作品级' }}</NButton>
          </NSpace>

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

        <!-- 文风对比:目标 vs 实测,每维每桶双条并排(合并原两张卡,去重) -->
        <NCard size="small" title="文风对比(目标 vs 实测)">
          <template #header-extra>
            <NSpace :size="6">
              <NTag v-if="workCfg?._source_work" size="small" type="info" round>目标:{{ workCfg._source_work }}</NTag>
              <NTag v-if="actual?.fingerprint" size="small" round>实测:{{ actual.chapter_count }}章/{{ actual.paragraph_count }}段</NTag>
            </NSpace>
          </template>
          <NAlert v-if="!actual?.fingerprint" type="default" :bordered="false">尚无已写章节可实测;先写章或导入参考作品设目标。</NAlert>
          <template v-else>
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
                <!-- 单值维度:目标/实测并列 -->
                <div v-if="(workCfg as any)?.[dim]?.value !== undefined" class="dual-single">
                  <span class="cmp-tag target">目标 {{ dim === 'dialogue_ratio' ? pct((workCfg as any)[dim].value) + '%' : (workCfg as any)[dim].value + '/k' }}</span>
                  <span class="cmp-tag actual">实测 {{ actual.fingerprint[dim] ? (dim === 'dialogue_ratio' ? pct(actual.fingerprint[dim].value) + '%' : actual.fingerprint[dim].value + '/k') : '—' }}</span>
                </div>
                <!-- 直方图维度:每桶双条(上灰=目标,下彩=实测) -->
                <div v-else>
                  <div v-for="row in dimRows(dim)" :key="row.k" class="bar-row">
                    <span class="bar-k" :class="{ hi: dim === 'structure' && row.k === 'notXisY' }">{{ row.k }}</span>
                    <div class="dual-bars">
                      <NProgress type="line" :percentage="pct(row.target)" :height="6" :show-indicator="false" color="#aaa" />
                      <NProgress type="line" :percentage="pct(row.actual)" :height="6" :show-indicator="false"
                        :status="(dim === 'structure' && row.k === 'notXisY' && pct(row.actual) > 2) ? 'warning' : 'success'" />
                    </div>
                    <span class="bar-v">{{ pct(row.actual) }}<span class="dim">/{{ pct(row.target) }}</span></span>
                  </div>
                </div>
              </div>
            </div>
            <div class="legend"><span class="cmp-tag target">灰=目标</span><span class="cmp-tag actual">彩=实测</span><span style="opacity:.5">右上 实测/目标</span></div>
          </template>
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
.bar-v { min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
.bar-v .dim { opacity: 0.45; }
.dual-bars { flex: 1; display: flex; flex-direction: column; gap: 1px; }
.dual-single { display: flex; gap: 10px; padding: 4px 0; font-size: 13px; }
.legend { margin-top: 8px; display: flex; gap: 12px; font-size: 11px; opacity: 0.7; }
.cmp-tag { font-size: 11px; }
.cmp-tag.target { color: #888; }
.cmp-tag.actual { color: var(--n-primary-color); font-weight: 600; }
</style>
