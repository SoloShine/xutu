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
import { useThemeStore } from '../stores/theme'

const props = defineProps<{ wid: string }>()
const msg = useMessage()
const theme = useThemeStore()
// 直方图配色随主题:实测=主色,目标=中性灰(按 mode 取,浅/深都可见)
const actualBarColor = computed(() => theme.primary)
const targetBarColor = computed(() => theme.mode === 'dark' ? '#4a505c' : '#c8ced8')

interface DimDef { label: string; unit: string; formula: string; interpret: string }
interface Fingerprint { _scope?: string; _volume_id?: number; _source_work?: string; _directive?: string; _directive_source?: string; _directive_stale?: boolean; _sample_info?: { stat_range?: [number, number]; stat_count?: number; stat_titles?: string[]; llm_sample_titles?: string[] }; _scalar_targets?: Record<string, number>; [k: string]: any }
const configs = ref<Fingerprint[]>([])
const dimDefs = ref<Record<string, DimDef>>({})
const volumes = ref<{ id: number; name: string }[]>([])
const actual = ref<{ fingerprint: Fingerprint | null; scalars: Record<string, number> | null; chapter_count: number; paragraph_count: number; cached?: boolean; computed_at?: string } | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const importPath = ref('')
const importing = ref(false)
const rangeStart = ref<number|null>(null), rangeEnd = ref<number|null>(null)
// 抽样控制 + base 来源
const baseSource = ref<'reference'|'self'>('reference')
const sampleStrategy = ref('spread')
const sampleCount = ref<number|null>(null)   // null=自动(sqrt 公式)
const wrStart = ref<number|null>(null), wrEnd = ref<number|null>(null)  // 本作已写章 global_number 范围
const previewExtract = ref<any>(null)        // 预览提取结果(不落库)
const previewingExtract = ref(false)
const STRATEGY_OPTS = [
  { label: '分散(多点,稳)', value: 'spread' },
  { label: '连续(取一段弧)', value: 'consecutive' },
  { label: '随机(可复现)', value: 'random' },
  { label: '全部', value: 'all' },
]
// 文件选择 + 预览
const fileName = ref('')
const fileText = ref('')
const fileEnc = ref('UTF-8')
const preview = ref<{chapter_count:number;chunked:boolean;sample_titles:string[];total_chars:number}|null>(null)
const previewing = ref(false)
const refreshing = ref(false)

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
    dash: fp.dash_density ? fp.dash_density.value : null,   // /千字(长度归一),非按段
    notx: fp.notXisY ? Math.round((fp.notXisY.rate || 0) * 1000) / 10 : null,
    dlg: fp.dialogue_ratio ? Math.round((fp.dialogue_ratio.value || 0) * 1000) / 10 : null,
    rhet: fp.rhetoric ? fp.rhetoric.value : null,
  }
})

// 当前有效目标标量(显式 scalar_targets 覆盖指纹派生)
const targetScalars = computed(() => {
  const st = workCfg.value?._scalar_targets || {}
  const d = derived.value
  return {
    dash: st.dash_density != null ? st.dash_density : d.dash,
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
  tDash.value = st.dash_density != null ? st.dash_density : null
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
    || scalarsPayload().dash_density !== st.dash_density
    || scalarsPayload().notXisY_rate !== st.notXisY_rate
    || scalarsPayload().dialogue_ratio !== st.dialogue_ratio
    || scalarsPayload().rhetoric_per_k !== st.rhetoric_per_k
})
function scalarsPayload() {
  const o: Record<string, number> = {}
  if (tDash.value != null) o.dash_density = tDash.value          // /千字(长度归一)
  if (tNotx.value != null) o.notXisY_rate = tNotx.value / 100
  if (tDlg.value != null) o.dialogue_ratio = tDlg.value / 100
  if (tRhet.value != null) o.rhetoric_per_k = tRhet.value
  return o
}

// 预设:一组标量目标快捷设定(dash/rhet 为 /千字;notx/dlg 为 %)
function applyPreset(name: string) {
  if (name === '冷硬快节奏') { tDash.value = 1; tNotx.value = 0.2; tDlg.value = 25; tRhet.value = 2 }
  else if (name === '平稳叙事') { tDash.value = 3; tNotx.value = 0.5; tDlg.value = 15; tRhet.value = 3 }
  else if (name === '浓修辞') { tDash.value = 4; tNotx.value = 0.5; tDlg.value = 20; tRhet.value = 8 }
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

// 维度分组(替代原 12 卡平铺)。隐藏 dash/period(按段,长度耦合,DIM_DEFINITIONS 自标"仅展示不可靠")
// 与 structure(与 sentence_length 重复)——数据仍在指纹,只是不渲染。
const HIST_GROUPS = [
  { title: '节奏分布', hint: '句长/段长 直方图', dims: ['sentence_length', 'paragraph_length'] },
  { title: '质感分布', hint: '对白类型/感官 直方图', dims: ['dialogue', 'sensory'] },
]
// 核心气味与密度(style-check 实际比对的标量)——合并成一张表,不再各自一张卡
const SCALAR_ROWS = [
  { dim: 'dash_density', better: 'low' },
  { dim: 'notXisY', better: 'low' },
  { dim: 'rhetoric', better: 'low' },
  { dim: 'period_density', better: 'low' },
  { dim: 'dialogue_ratio', better: 'target' },
]
function fmtVal(dim: string, v: number | null): string | null {
  if (v == null) return null
  return dim === 'dialogue_ratio' ? pct(v) + '%' : (Math.round(v * 100) / 100) + '/k'
}
// 该标量是否明显偏离(低越好型:超 target×1.5;对白比:差>25pp)
function scalarOver(dim: string, actual: number | null, target: number | null): boolean {
  if (actual == null || target == null) return false
  if (dim === 'dialogue_ratio') return Math.abs(actual - target) > 0.25
  return actual > target * 1.5 + 0.01
}
function pct(n: number) { return Math.round((n || 0) * 1000) / 10 }

// 导入参考作品(本地 txt 路径,服务端纯程序提取)
// 导入参考作品(本地 txt 路径,服务端纯程序提取)
async function refreshActual() {
  refreshing.value = true
  try {
    actual.value = await api.styleActual(props.wid, undefined, true) as any
    msg.success(actual.value?.cached ? '实测已重算并刷新缓存' : '已重算')
  } catch (e:any) { msg.error('刷新失败: '+(e.message||e)) }
  finally { refreshing.value = false }
}

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

// 预览提取结果(不落库):给抽样参数→返回关键标量+抽样章名,供 A/B 对比不同范围/策略
async function doPreviewExtract() {
  if (!fileText.value) { msg.warning('先选择参考作品 txt'); return }
  previewingExtract.value = true
  try {
    const body: any = { strategy: sampleStrategy.value, sample: sampleCount.value ?? undefined, text: fileText.value }
    if (rangeStart.value != null && rangeEnd.value != null) body.chapter_range = [rangeStart.value, rangeEnd.value]
    const r: any = await api.previewExtract(props.wid, body)
    if (r && r.ok !== false) { previewExtract.value = r.item; msg.success(`预览:${r.item.sampled_chapters}章/${r.item.sample_range?.[0]}-${r.item.sample_range?.[1]}`) }
    else msg.error('预览失败: '+((r&&r.error)||''))
  } catch (e:any) { msg.error('预览失败: '+(e.message||e)) }
  finally { previewingExtract.value = false }
}

// 从本作已写章节提取作 base(自洽提升为显式来源)
async function importWritten() {
  importing.value = true
  try {
    const body: any = { scope: scope.value, strategy: sampleStrategy.value, sample: sampleCount.value ?? undefined,
      volume_id: scope.value === 'volume' ? volumeId.value : undefined }
    if (wrStart.value != null && wrEnd.value != null) body.chapter_range = [wrStart.value, wrEnd.value]
    const r: any = await api.extractWritten(props.wid, body)
    if (r && r.ok !== false) {
      const it = r.item || {}
      msg.success(`已提取本作已写:${it.sampled_chapters||'?'}章(共${it.chapter_count||'?'}章)`)
      await load()
    } else msg.error('提取失败: '+((r&&r.error)||'无已写章节'))
  } catch (e:any) { msg.error('提取失败: '+(e.message||e)) }
  finally { importing.value = false }
}
function peVal(k: string) { return previewExtract.value?.scalars?.[k] }  // 预览标量取值
function entries(fp: Fingerprint, key: string): [string, number][] {
  const d = fp[key]; if (!d || typeof d !== 'object') return []
  return Object.entries(d).filter(([k]) => !k.startsWith('_')) as [string, number][]
}
// 某 dim 各桶的目标+实测值(实测优先作桶源——没参考也显示实测)
function dimRows(dim: string) {
  const t = (workCfg.value as any)?.[dim] || {}
  const a = (actual.value?.fingerprint as any)?.[dim] || {}
  const src = Object.keys(a).length ? a : t
  return Object.keys(src).filter(k => !k.startsWith('_') && k !== 'value').map(k => ({ k, target: t[k] || 0, actual: a[k] || 0 }))
}
// 单值维度的值(实测/目标),无则 null
function dimSingle(dim: string, side: 'actual' | 'target'): number | null {
  const src = side === 'actual' ? (actual.value?.fingerprint as any)?.[dim] : (workCfg.value as any)?.[dim]
  return src && src.value !== undefined ? src.value : null
}
function defOf(key: string) { return dimDefs.value[key] }
</script>

<template>
  <div class="style-view">
    <NSpin :show="loading">
      <div v-if="error" style="color: var(--br-warning)">{{ error }}</div>

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
            <NTag v-else size="small" type="primary" round>全作品生效</NTag>
          </NSpace>

          <NAlert v-if="scope === 'volume' && !curCfg" type="default" :bordered="false" style="margin-bottom:8px">
            该卷尚未设覆盖,保存后将创建卷级配置(只存你填的字段,其余继承作品级)。
          </NAlert>

          <!-- 提取文风目标 base:来源(参考作品/本作已写)+ 抽样控制 + 预览 A/B。纯程序零LLM。 -->
          <div class="field-label">提取文风目标(base) → 指纹 + 派生指令</div>
          <NRadioGroup v-model:value="baseSource" size="small" style="margin-bottom:8px">
            <NRadioButton value="reference">参考作品</NRadioButton>
            <NRadioButton value="self">本作已写章节</NRadioButton>
          </NRadioGroup>

          <!-- 共享抽样控制:策略 + 数量 -->
          <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
            <span class="knob-label">抽样</span>
            <NSelect v-model:value="sampleStrategy" size="small" :options="STRATEGY_OPTS" style="width:150px" />
            <span class="knob-label">数量(留空=自动)</span>
            <NInputNumber v-model:value="sampleCount" :min="1" size="small" placeholder="自动" style="width:90px" />
          </NSpace>

          <!-- 参考作品分支 -->
          <template v-if="baseSource === 'reference'">
            <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
              <input id="style-file-input" type="file" accept=".txt,.text" style="display:none" @change="onFilePick" />
              <NButton size="small" @click="pickFile">选择 txt 文件</NButton>
              <NTag v-if="fileName" size="small" type="primary" round>{{ fileName }}</NTag>
              <span class="knob-label">编码</span>
              <NSelect v-model:value="fileEnc" size="small" :options="[{label:'UTF-8',value:'UTF-8'},{label:'GBK',value:'GBK'},{label:'GB18030',value:'GB18030'}]" style="width:110px" />
            </NSpace>
            <NAlert v-if="preview" :type="preview.chunked ? 'warning' : 'info'" :bordered="false" style="margin-bottom:8px">
              <b>{{ preview.chapter_count }}</b> 章 · {{ preview.total_chars }} 字
              <NTag v-if="preview.chunked" size="tiny" type="warning" round>非标准章名→按字数切片</NTag>
              <div style="opacity:.7;font-size:12px;margin-top:2px">样章: {{ preview.sample_titles.join(' / ') }}</div>
            </NAlert>
            <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
              <span class="knob-label">章范围(留空=中段)</span>
              <NInputNumber v-model:value="rangeStart" :min="1" :max="preview?.chapter_count" size="small" :placeholder="preview?`1`:'起'" style="width:80px" />
              <span>~</span>
              <NInputNumber v-model:value="rangeEnd" :min="1" :max="preview?.chapter_count" size="small" :placeholder="preview?`${preview.chapter_count}`:'止'" style="width:80px" />
              <NButton size="small" :loading="previewingExtract" :disabled="!fileText" @click="doPreviewExtract">预览结果</NButton>
              <NButton size="small" type="primary" :loading="importing" :disabled="!fileText" @click="importRef">提取→{{ scope === 'volume' ? '卷级' : '作品级' }}</NButton>
            </NSpace>
            <!-- 预览结果(不落库):不同范围/策略→不同指纹,提交前 A/B -->
            <NAlert v-if="previewExtract" type="success" :bordered="false" style="margin-bottom:8px">
              <b>预览</b>:抽 {{ previewExtract.sampled_chapters }} 章 / {{ previewExtract.sample_range?.[0] }}-{{ previewExtract.sample_range?.[1] }}
              <span style="margin-left:8px;opacity:.8">破折号 {{ peVal('dash_density') }}/k · 不是A是B {{ peVal('notXisY')?.value }}/k · 句号 {{ peVal('period_density') }}/k · 对白 {{ Math.round((peVal('dialogue_ratio')||0)*1000)/10 }}% · 修辞 {{ peVal('rhetoric') }}/k</span>
              <div style="opacity:.6;font-size:11px;margin-top:2px">改范围/策略/数量再「预览结果」对比,挑最贴合的再「提取」</div>
            </NAlert>
          </template>

          <!-- 本作已写分支:把自洽提升为显式 base 来源 -->
          <template v-else>
            <NAlert type="info" :bordered="false" style="margin-bottom:8px">
              用作品【已写】章节(status=writing/completed)的文风作目标——适合"向自己已建立的风格看齐",无需外部参考。
              <span style="opacity:.7">。range 按 global_number 过滤(留空=全部已写)。</span>
            </NAlert>
            <NSpace :size="6" align="center" wrap style="margin-bottom:8px">
              <span class="knob-label">章范围(global_number,留空=全部已写)</span>
              <NInputNumber v-model:value="wrStart" :min="1" size="small" placeholder="起" style="width:80px" />
              <span>~</span>
              <NInputNumber v-model:value="wrEnd" :min="1" size="small" placeholder="止" style="width:80px" />
              <NButton size="small" type="primary" :loading="importing" @click="importWritten">提取→{{ scope === 'volume' ? '卷级' : '作品级' }}</NButton>
            </NSpace>
          </template>


          <!-- 文风指令 -->
          <div class="field-label">文风指令(定性,注入 writer)</div>
          <NAlert v-if="workCfg?._directive_stale" type="warning" :bordered="false" style="margin-bottom:6px">
            指令来自旧参考「{{ workCfg._directive_source }}」,与当前指纹「{{ workCfg._source_work }}」不匹配。
            运行 <code>/analyze-style {{ props.wid }}</code> 重新分析。
          </NAlert>
          <NInput v-model:value="directive" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
            :placeholder="scope === 'volume' ? '留空=继承作品级指令' : '短促冷硬、镜头式白描、不用心理独白...'" />

          <!-- 4 标量目标(可编辑,空=指纹派生) -->
          <div class="field-label" style="margin-top:10px">
            标量目标(style-check 比对;留空=用指纹派生值)
          </div>
          <div class="scalar-grid">
            <div class="scalar"><span>破折号(/千字,长度归一)</span><NInputNumber v-model:value="tDash" :min="0" :step="0.5" size="small" :placeholder="derived.dash != null ? String(derived.dash) : ''" /></div>
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
              <NTooltip v-if="workCfg?._source_work" trigger="hover" placement="bottom">
                <template #trigger>
                  <NTag size="small" type="primary" round style="cursor:help">目标:{{ workCfg._source_work }}</NTag>
                </template>
                <div style="max-width:320px">
                  <div><b>统计抽样</b>(指纹来源):{{ (workCfg._sample_info?.stat_count) || '?' }}章,范围
                    {{ workCfg._sample_info?.stat_range?.[0] }}-{{ workCfg._sample_info?.stat_range?.[1] }}</div>
                  <div style="opacity:.7;font-size:12px;margin:2px 0">{{ (workCfg._sample_info?.stat_titles || []).join(' / ') }}</div>
                  <div v-if="workCfg._sample_info?.llm_sample_titles?.length" style="margin-top:4px">
                    <b>文风指令抽样</b>:/analyze-style 读这 {{ workCfg._sample_info.llm_sample_titles.length }} 章</div>
                  <div style="opacity:.7;font-size:12px;margin:2px 0">{{ (workCfg._sample_info?.llm_sample_titles || []).join(' / ') }}</div>
                </div>
              </NTooltip>
              <NTag v-if="actual?.fingerprint" size="small" round :title="actual.cached ? ('缓存于 '+actual.computed_at) : '实时'">
                实测:{{ actual.chapter_count }}章/{{ actual.paragraph_count }}段{{ actual.cached ? '·缓存' : '' }}
              </NTag>
              <NButton v-if="actual?.fingerprint" size="tiny" quaternary :loading="refreshing" @click="refreshActual">刷新实测</NButton>
            </NSpace>
          </template>
          <NAlert v-if="!actual?.fingerprint" type="default" :bordered="false">尚无已写章节可实测;先写章或导入参考作品设目标。</NAlert>
          <template v-else>
            <!-- 核心气味与密度:一张表(style-check 实际比对的标量,合并原 5 张单值卡) -->
            <div class="style-section">
              <div class="section-title">气味与密度 <span class="section-hint">style-check 比对核心;橙=明显偏离</span></div>
              <table class="scalar-table">
                <thead><tr><th>指标</th><th class="num">实测</th><th class="num">目标</th></tr></thead>
                <tbody>
                  <tr v-for="r in SCALAR_ROWS" :key="r.dim">
                    <td class="lbl">
                      <NTooltip trigger="hover" placement="top">
                        <template #trigger><span class="lbl-inner">{{ defOf(r.dim)?.label || r.dim }}<svg class="dim-info-icon" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.2a.9.9 0 110 1.8.9.9 0 010-1.8zm1.1 8.2H6.9c0-.5.4-.7.4-1.2V8.6c0-.4-.2-.5-.6-.6v-.5h2.4v3.4c0 .6.3.8.3 1.1z"/></svg></span></template>
                        <div style="max-width:260px"><div><b>{{ defOf(r.dim)?.label }}</b> ({{ defOf(r.dim)?.unit }})</div><div style="opacity:.8">{{ defOf(r.dim)?.formula }}</div><div style="opacity:.65;margin-top:4px">{{ defOf(r.dim)?.interpret }}</div></div>
                      </NTooltip>
                    </td>
                    <td class="num" :class="{ over: scalarOver(r.dim, dimSingle(r.dim,'actual'), dimSingle(r.dim,'target')) }">{{ fmtVal(r.dim, dimSingle(r.dim,'actual')) || '—' }}</td>
                    <td class="num tgt">{{ fmtVal(r.dim, dimSingle(r.dim,'target')) || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- 分布直方图:按主题分组,每组若干维度卡(双条 灰目标/彩实测) -->
            <div v-for="g in HIST_GROUPS" :key="g.title" class="style-section">
              <div class="section-title">{{ g.title }} <span class="section-hint">{{ g.hint }}</span></div>
              <div class="dim-grid">
                <div v-for="dim in g.dims" :key="dim" class="dim">
                  <div class="dim-head">
                    <NTooltip trigger="hover" placement="top">
                      <template #trigger><span class="dim-label">{{ defOf(dim)?.label || dim }}<svg class="dim-info-icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.2a.9.9 0 110 1.8.9.9 0 010-1.8zm1.1 8.2H6.9c0-.5.4-.7.4-1.2V8.6c0-.4-.2-.5-.6-.6v-.5h2.4v3.4c0 .6.3.8.3 1.1z"/></svg></span></template>
                      <div style="max-width:280px">
                        <div><b>{{ defOf(dim)?.label }}</b> ({{ defOf(dim)?.unit }})</div>
                        <div style="opacity:.8">{{ defOf(dim)?.formula }}</div>
                        <div style="opacity:.65;margin-top:4px">{{ defOf(dim)?.interpret }}</div>
                      </div>
                    </NTooltip>
                  </div>
                  <div v-for="row in dimRows(dim)" :key="row.k" class="bar-row">
                    <span class="bar-k">{{ row.k }}</span>
                    <div class="dual-bars">
                      <NProgress type="line" :percentage="pct(row.target)" :height="6" :show-indicator="false" :color="targetBarColor" />
                      <NProgress type="line" :percentage="pct(row.actual)" :height="6" :show-indicator="false" :color="actualBarColor" />
                    </div>
                    <span class="bar-v">{{ pct(row.actual) }}<span class="tgt-val">/{{ pct(row.target) }}</span></span>
                  </div>
                </div>
              </div>
            </div>
            <div class="legend"><span class="cmp-tag target">灰=目标</span><span class="cmp-tag actual">彩=实测</span><span style="opacity:.5">分布卡右上 实测/目标</span></div>
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
.style-section { margin-top: 14px; }
.style-section:first-of-type { margin-top: 4px; }
.section-title { font-size: 13px; font-weight: 600; opacity: 0.85; margin-bottom: 8px; display: flex; align-items: baseline; gap: 8px; }
.section-hint { font-size: 11px; font-weight: 400; opacity: 0.55; }
.scalar-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.scalar-table th { text-align: left; font-size: 11px; opacity: 0.55; font-weight: 500; padding: 4px 8px; border-bottom: 1px solid var(--br-border); }
/* 数值列:收窄到内容宽(width:1%+nowrap 让标签列吃剩余空间)+ 表头右对齐齐于数值,
   大屏下表头与数值紧贴右侧,不再隔很远 */
.scalar-table th.num, .scalar-table td.num { text-align: right; white-space: nowrap; width: 1%; }
/* 行分隔线用 --br-border-soft(随 mode);旧 fallback rgba(255,255,255,.06) 在浅色下不可见 */
.scalar-table td { padding: 6px 8px; border-bottom: 1px solid var(--br-border-soft); }
.scalar-table td.num { font-variant-numeric: tabular-nums; font-weight: 600; }
.scalar-table td.num.over { color: var(--br-warning); }
.scalar-table td.tgt { opacity: 0.6; font-weight: 400; }
.scalar-table td.lbl { font-weight: 500; }
.lbl-inner { display: inline-flex; align-items: center; gap: 3px; cursor: help; }
.dim { background: var(--br-card); border: 1px solid var(--br-border); border-radius: 8px; padding: 10px; }
.dim-label { font-weight: 600; cursor: help; display: inline-flex; align-items: center; gap: 3px; }
.dim-info-icon { fill: currentColor; opacity: 0.5; transition: opacity .15s; }
.dim-label:hover .dim-info-icon { opacity: 0.9; }
.single-val { font-size: 20px; font-weight: 700; color: var(--br-primary); padding: 4px 0; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; font-size: 12px; }
.bar-k { min-width: 56px; opacity: 0.8; }
.bar-k.hi { color: var(--br-warning); font-weight: 700; }
.bar-v { min-width: 42px; text-align: right; font-variant-numeric: tabular-nums; }
.cmp-table { display: flex; flex-direction: column; gap: 8px; }
.cmp-row { display: flex; align-items: center; gap: 10px; }
.cmp-row.over .cmp-label { color: var(--br-warning); font-weight: 700; }
.cmp-label { min-width: 110px; font-size: 13px; }
.cmp-bars { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.cmp-line { display: flex; align-items: center; gap: 6px; }
.cmp-tag { font-size: 10px; min-width: 28px; opacity: 0.6; }
.cmp-tag.actual { color: var(--br-primary); opacity: 1; }
.bar-v { min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
.bar-v .tgt-val { opacity: 0.45; }
.dual-bars { flex: 1; display: flex; flex-direction: column; gap: 1px; }
.dual-single { display: flex; gap: 10px; padding: 4px 0; font-size: 13px; }
.legend { margin-top: 8px; display: flex; gap: 12px; font-size: 11px; opacity: 0.7; }
.cmp-tag { font-size: 11px; }
.cmp-tag.target { color: var(--br-text3); }
.cmp-tag.actual { color: var(--br-primary); font-weight: 600; }
</style>
