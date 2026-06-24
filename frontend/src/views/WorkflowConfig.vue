<!-- src/views/WorkflowConfig.vue -->
<!-- 编排旋钮配置（runner-agnostic，phase 1 冻结自 .js 硬编码快照）。
     scope:作品级(基线) / 卷级(覆盖,逐键 merge)。文风项不在此(在文风指纹页,RC3 单真相源)。
     消费方:LangGraph runner(经 CLI get-workflow-config);当前 .js 不读,保持现状。 -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import {
  NSpin, NEmpty, NCard, NSpace, NAlert, NInput, NInputNumber, NButton,
  NRadioGroup, NRadioButton, NSelect, NSwitch, NTag, useMessage,
} from 'naive-ui'
import { api } from '../api/client'
import { useThemeStore } from '../stores/theme'

const props = defineProps<{ wid: string }>()
const msg = useMessage()
const theme = useThemeStore()

type Cat = 'caps' | 'models' | 'phases' | 'prompts'
interface CfgRow { id: number; scope: 'work' | 'volume'; volume_id: number | null; caps: Record<string, any>; models: Record<string, any>; phases: Record<string, any>; prompts: Record<string, any>; updated_at: string }

const configs = ref<CfgRow[]>([])
const defaults = ref<Record<Cat, Record<string, any>>>({ caps: {}, models: {}, phases: {}, prompts: {} })
const volumes = ref<{ id: number; name: string }[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const scope = ref<'work' | 'volume'>('work')
const volumeId = ref<number | null>(null)

// 旋钮元数据(驱动渲染 + 标注 .js 来源)
const CAP_META = [
  { key: 'writer', label: 'Writer 迭代上限', hint: 'chapter.js · 写作自纠结构' },
  { key: 'editor', label: 'Editor 迭代上限', hint: 'chapter.js · Revise 自纠' },
  { key: 'repair', label: 'Repair 轮数', hint: 'chapter-edit.js' },
  { key: 'style', label: 'Style 收敛轮数', hint: 'chapter-edit.js · STYLE_MAX_ROUNDS' },
  { key: 'vr_fix', label: '卷审 Fix 轮数', hint: 'volume-review.js · VR_FIX_ROUNDS' },
]
const MODEL_KEYS = [
  'writer', 'editor', 'consistency', 'rewrite', 'polish', 'surgical', 'repair', 'style',
  'volume_review', 'volume_fix', 'volume_recheck', 'author',
]
// 全局端点目录(供每个流程选 endpoint;model 从该端点的 models 列表选)
const endpoints = ref<{ name: string; models: string[] }[]>([])
const endpointOpts = () => [
  { label: '(未配置)', value: null },
  ...endpoints.value.map(e => ({ label: e.name, value: e.name })),
] as any[]
function modelOptsFor(epName: string | null) {
  if (!epName) return []
  const ep = endpoints.value.find(e => e.name === epName)
  return (ep?.models || []).map(m => ({ label: m, value: m }))
}
const PHASE_BOOL_META = [
  { key: 'consistency', label: 'Consistency 阶段', hint: '每章代词/性别一致性 ops' },
  { key: 'consistency_requires_characters', label: 'Consistency 需角色正典', hint: '无角色正典则跳过' },
  { key: 'proper_nouns', label: '专名硬校验', hint: '跨章角色/地名一致' },
  { key: 'edit_style_convergence', label: '编辑 Style 收敛', hint: '仅 rewrite/polish 模式' },
]
const PROMPT_META = [
  { key: 'writer', label: 'Writer prompt', hint: '.claude/templates/bedrock/chapter_writer.md' },
  { key: 'editor', label: 'Editor prompt', hint: '.claude/templates/bedrock/edit_agent.md' },
  { key: 'volume_review', label: 'VolumeReview prompt', hint: '.claude/templates/bedrock/volume_review.md' },
]

// 编辑态:当前 scope 的有效值(逐键 merge: 默认 ← work 行 ← volume 行)
const caps = ref<Record<string, number>>({})
const models = ref<Record<string, { endpoint: string | null; model: string | null }>>({})
const phases = ref<Record<string, any>>({})
const prompts = ref<Record<string, string>>({})

const workRow = computed(() => configs.value.find(c => c.scope === 'work') || null)
const volRow = computed(() => configs.value.find(c => c.scope === 'volume' && c.volume_id === volumeId.value) || null)

// 深度逐键 merge:默认 ← work ← volume(None/缺失不覆盖),与后端 get_workflow_config 同语义
function effective(): { caps: Record<string, any>; models: Record<string, any>; phases: Record<string, any>; prompts: Record<string, any> } {
  // 按 category 取(行里 caps/models/phases/prompts 是字段名)
  const pick = (cat: Cat, ...rows: (CfgRow | null)[]) => {
    const out: Record<string, any> = { ...(defaults.value[cat] || {}) }
    for (const r of rows) {
      if (!r) continue
      for (const [k, v] of Object.entries((r as any)[cat] || {})) {
        if (v === null || v === undefined) continue
        out[k] = v
      }
    }
    return out
  }
  return {
    caps: pick('caps', workRow.value, scope.value === 'volume' ? volRow.value : null),
    models: pick('models', workRow.value, scope.value === 'volume' ? volRow.value : null),
    phases: pick('phases', workRow.value, scope.value === 'volume' ? volRow.value : null),
    prompts: pick('prompts', workRow.value, scope.value === 'volume' ? volRow.value : null),
  }
}

function populate() {
  const e = effective()
  caps.value = { ...e.caps }
  // models:绑定 {endpoint, model}(兼容旧格式纯字符串 model + null)
  models.value = Object.fromEntries(MODEL_KEYS.map(k => {
    const b = e.models[k]
    const binding = (b && typeof b === 'object')
      ? { endpoint: b.endpoint ?? null, model: b.model ?? null }
      : (typeof b === 'string' && b ? { endpoint: null, model: b } : { endpoint: null, model: null })
    return [k, binding]
  }))
  phases.value = { ...e.phases }
  prompts.value = { ...e.prompts }
}

async function load() {
  if (!props.wid) return
  loading.value = true; error.value = ''
  try {
    const [r, eps] = await Promise.all([api.workflowConfig(props.wid), api.endpoints() as any])
    configs.value = r.configs || []
    defaults.value = r.defaults || { caps: {}, models: {}, phases: {}, prompts: {} }
    volumes.value = r.volumes || []
    endpoints.value = (eps || []).map((e: any) => ({ name: e.name, models: e.models || [] }))
    if (volumes.value.length && volumeId.value == null) volumeId.value = volumes.value[0].id
    populate()
  } catch (e: any) { error.value = e.message || String(e) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })
watch([scope, volumeId], populate)

// dirty:当前编辑态 ≠ 当前 scope 有效值
const dirty = computed(() => {
  const e = effective()
  const eq = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b)
  const normBinding = (b: any) => {
    const bb = (b && typeof b === 'object') ? b : (typeof b === 'string' && b ? { endpoint: null, model: b } : null)
    return bb ? { endpoint: bb.endpoint ?? null, model: bb.model ?? null } : { endpoint: null, model: null }
  }
  const modelsCur = Object.fromEntries(MODEL_KEYS.map(k => [k, normBinding(models.value[k])]))
  const modelsEff = Object.fromEntries(MODEL_KEYS.map(k => [k, normBinding(e.models[k])]))
  return !eq(caps.value, e.caps) || !eq(modelsCur, modelsEff)
    || !eq(phases.value, e.phases) || !eq(prompts.value, e.prompts)
})

async function save() {
  saving.value = true
  try {
    // 写入选定 scope 的完整 4 类(models={process:{endpoint,model}})
    const modelsPayload: Record<string, any> = {}
    for (const k of MODEL_KEYS) {
      const b = models.value[k] || { endpoint: null, model: null }
      modelsPayload[k] = { endpoint: b.endpoint || null, model: b.model || null }
    }
    await api.setWorkflowConfig(props.wid, {
      scope: scope.value,
      volume_id: scope.value === 'volume' ? volumeId.value : undefined,
      caps: { ...caps.value },
      models: modelsPayload,
      phases: { ...phases.value },
      prompts: { ...prompts.value },
    })
    msg.success(`${scope.value === 'volume' ? '卷级' : '作品级'}工作流配置已保存`)
    await load()
  } catch (e: any) { msg.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

function phaseSelectOpts() {
  return [
    { label: 'auto（指纹门控）', value: 'auto' },
    { label: 'on（强制启用）', value: 'on' },
    { label: 'off（禁用）', value: 'off' },
  ]
}
const isVolume = computed(() => scope.value === 'volume')
</script>

<template>
  <NSpin :show="loading">
    <NAlert v-if="error" type="error" style="margin-bottom:12px" :show-icon="true">{{ error }}</NAlert>
    <NEmpty v-if="!loading && !configs.length && false" />
    <div v-if="!loading">
      <!-- 作用域 + 卷选择 -->
      <NCard size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
        <NSpace align="center">
          <NRadioGroup v-model:value="scope">
            <NRadioButton value="work">作品级（基线）</NRadioButton>
            <NRadioButton value="volume">卷级（覆盖）</NRadioButton>
          </NRadioGroup>
          <NSelect v-if="isVolume" v-model:value="volumeId" :options="volumes.map(v => ({ label: v.name, value: v.id }))"
                   placeholder="选择卷" style="width:180px" />
          <NTag v-if="isVolume" size="small" type="info">逐键 merge 覆盖作品级</NTag>
          <div style="flex:1"></div>
          <NButton type="primary" :disabled="!dirty" :loading="saving" @click="save">保存</NButton>
        </NSpace>
      </NCard>

      <NAlert type="info" style="margin-bottom:12px" :show-icon="true">
        这些旋钮当前由 <code>.js</code> 工作流硬编码;此处为 <strong>LangGraph runner</strong> 的配置入口(phase 1 冻结快照=现状)。
        文风项(字数/hygiene)在「文风指纹」页,不重复。
      </NAlert>

      <!-- caps -->
      <NCard title="迭代上限（caps）" size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
        <div class="grid2">
          <div v-for="m in CAP_META" :key="m.key" class="knob">
            <div class="knob-label">{{ m.label }} <span class="hint">{{ m.hint }}</span></div>
            <NInputNumber v-model:value="caps[m.key]" :min="0" :max="20" size="small" style="width:120px" />
          </div>
        </div>
      </NCard>

      <!-- models:每个流程选【全局端点 + 模型】= 配置 LangGraph 图时绑 LLM -->
      <NCard title="模型绑定（models · 每个流程选端点+模型）" size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
        <div class="hint" style="margin-bottom:8px">端点来自「LLM 端点」面板(全局目录);模型从该端点的模型列表选(可自由输入)。未配置的流程 runner 会明确报错。</div>
        <div class="grid2">
          <div v-for="k in MODEL_KEYS" :key="k" class="knob">
            <div class="knob-label">{{ k }}</div>
            <div class="model-row">
              <NSelect v-model:value="models[k].endpoint" :options="endpointOpts()" size="small"
                       style="width:150px" placeholder="端点" />
              <NSelect v-model:value="models[k].model" :options="modelOptsFor(models[k].endpoint)"
                       size="small" tag filterable style="width:200px" placeholder="模型" />
            </div>
          </div>
        </div>
      </NCard>

      <!-- phases -->
      <NCard title="阶段开关（phases）" size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
        <div class="knob" style="margin-bottom:14px">
          <div class="knob-label">polish 阶段 <span class="hint">chapter.js · fingerprint 门控</span></div>
          <NSelect v-model:value="phases.polish" :options="phaseSelectOpts()" size="small" style="width:200px" />
        </div>
        <div class="grid2">
          <div v-for="m in PHASE_BOOL_META" :key="m.key" class="knob">
            <div class="knob-label">{{ m.label }} <span class="hint">{{ m.hint }}</span></div>
            <NSwitch v-model:value="phases[m.key]" />
          </div>
        </div>
      </NCard>

      <!-- prompts -->
      <NCard title="Prompt 模板路径（prompts）" size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
        <div class="grid1">
          <div v-for="m in PROMPT_META" :key="m.key" class="knob">
            <div class="knob-label">{{ m.label }} <span class="hint">{{ m.hint }}</span></div>
            <NInput v-model:value="prompts[m.key]" size="small" placeholder=".md 路径" />
          </div>
        </div>
        <div class="hint" style="margin-top:8px">注:consistency/rewrite/polish/surgical/repair/style-polish 的 prompt 是 .js 内联函数,LangGraph 迁移时外化为文件后再配。</div>
      </NCard>
    </div>
  </NSpin>
</template>

<style scoped>
.grid2 { display:grid; grid-template-columns: repeat(2, 1fr); gap: 12px 24px; }
.grid1 { display:grid; grid-template-columns: 1fr; gap: 12px; }
.model-row { display: flex; gap: 8px; }
.knob { display:flex; flex-direction:column; gap:4px; }
.knob-label { font-size: 13px; color: var(--br-text1); }
.hint { font-size: 11px; color: var(--br-text3); margin-left:6px; }
code { background: var(--br-elevated, var(--br-card)); padding: 1px 4px; border-radius: 3px; }
</style>
