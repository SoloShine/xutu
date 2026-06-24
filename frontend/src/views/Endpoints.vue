<!-- src/views/Endpoints.vue -->
<!-- 全局 LLM 端点目录(跨项目共享,~/.bedrock/global.db)。
     每个:{name, provider, base_url, api_key, models[]}。api_key 永不回显(掩码)。
     作品级在「工作流配置」面板为每个流程选这里的端点+模型。 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { NSpin, NCard, NSpace, NInput, NSelect, NButton, NTag, NPopconfirm, NEmpty, NAlert, useMessage } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()

interface Endpoint { id: number; name: string; provider: string; base_url: string; api_key_set: boolean; api_key_tail: string; models: string[] }
const endpoints = ref<Endpoint[]>([])
const loading = ref(true)
const saving = ref(false)

// 新增/编辑表单
const name = ref(''), provider = ref('anthropic'), baseUrl = ref(''), apiKey = ref(''), modelsText = ref('')
const editingName = ref<string | null>(null)   // null=新增模式

const PROVIDER_OPTS = [
  { label: 'Anthropic(Claude)', value: 'anthropic' },
  { label: 'OpenAI(GPT)', value: 'openai' },
  { label: 'Google(Gemini)', value: 'google_genai' },
  { label: 'Ollama(本地)', value: 'ollama' },
]

async function load() {
  loading.value = true
  try { endpoints.value = await api.endpoints() as any }
  catch (e: any) { msg.error('加载端点失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })

function resetForm() {
  name.value = ''; provider.value = 'anthropic'; baseUrl.value = ''; apiKey.value = ''; modelsText.value = ''
  editingName.value = null
}

function edit(e: Endpoint) {
  editingName.value = e.name
  name.value = e.name; provider.value = e.provider; baseUrl.value = e.base_url
  apiKey.value = ''   // 不回显;留空=保留
  modelsText.value = e.models.join('\n')
}

async function save() {
  if (!name.value.trim()) { msg.warning('需填 name'); return }
  saving.value = true
  try {
    const body: any = {
      name: name.value.trim(), provider: provider.value, base_url: baseUrl.value,
      models: modelsText.value.split('\n').map(s => s.trim()).filter(Boolean),
    }
    if (apiKey.value) body.api_key = apiKey.value   // 留空=保留旧 key
    await api.upsertEndpoint(body)
    msg.success(`端点「${name.value}」已保存`)
    resetForm(); await load()
  } catch (e: any) { msg.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

async function remove(name2: string) {
  try {
    await api.deleteEndpoint(name2)
    msg.success(`端点「${name2}」已删`)
    if (editingName.value === name2) resetForm()
    await load()
  } catch (e: any) { msg.error('删除失败: ' + (e.message || e)) }
}
</script>

<template>
  <NSpin :show="loading">
    <NAlert type="info" style="margin-bottom:12px" :show-icon="true">
      <strong>全局</strong> LLM 端点目录(跨所有项目共享)。<strong>base_url</strong> 填第三方/代理;api_key 存本地,掩码不回显。
      作品级在「工作流配置」面板为每个流程选这里的端点 + 模型。
    </NAlert>

    <NCard title="端点列表" size="small" style="margin-bottom:12px" :content-style="{ background: 'var(--br-card)' }">
      <NEmpty v-if="!endpoints.length" description="暂无端点,下面新建" size="small" />
      <div v-for="e in endpoints" :key="e.name" class="ep-row">
        <div class="ep-head">
          <strong>{{ e.name }}</strong>
          <NTag size="tiny" :bordered="false">{{ e.provider }}</NTag>
          <NTag v-if="e.api_key_set" size="tiny" type="success" :bordered="false">key ****{{ e.api_key_tail }}</NTag>
          <NTag v-else size="tiny" type="warning" :bordered="false">无 key</NTag>
        </div>
        <div class="ep-meta">{{ e.base_url || '(官方端点)' }} · 模型: {{ e.models.join(', ') || '(无)' }}</div>
        <NSpace :size="8">
          <NButton size="tiny" @click="edit(e)">编辑</NButton>
          <NPopconfirm @positive-click="remove(e.name)"><template #trigger><NButton size="tiny" type="error" ghost>删</NButton></template>删端点「{{ e.name }}」?</NPopconfirm>
        </NSpace>
      </div>
    </NCard>

    <NCard :title="editingName ? `编辑「${editingName}」` : '新建端点'" size="small" :content-style="{ background: 'var(--br-card)' }">
      <NSpace vertical :size="12">
        <div><div class="lbl">名称(唯一)</div><NInput v-model:value="name" :disabled="!!editingName" placeholder="claude-proxy" /></div>
        <div><div class="lbl">提供商</div><NSelect v-model:value="provider" :options="PROVIDER_OPTS" style="width:280px" /></div>
        <div><div class="lbl">Base URL <span class="hint">空=官方;非空=第三方/代理</span></div><NInput v-model:value="baseUrl" placeholder="https://api.proxy.com" /></div>
        <div><div class="lbl">API Key <span class="hint">{{ editingName ? '留空=保留旧 key' : '' }}</span></div><NInput v-model:value="apiKey" type="password" show-password-on="click" placeholder="sk-..." /></div>
        <div><div class="lbl">模型(每行一个)</div><NInput v-model:value="modelsText" type="textarea" :rows="3" placeholder="claude-sonnet-4-6&#10;claude-opus-4-8" /></div>
        <NSpace>
          <NButton type="primary" :loading="saving" @click="save">{{ editingName ? '保存修改' : '新建' }}</NButton>
          <NButton v-if="editingName" @click="resetForm">取消编辑</NButton>
        </NSpace>
      </NSpace>
    </NCard>
  </NSpin>
</template>

<style scoped>
.ep-row { padding: 8px 0; border-bottom: 1px solid var(--br-border-soft); }
.ep-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ep-meta { font-size: 12px; color: var(--br-text3); margin-bottom: 6px; }
.lbl { font-size: 13px; color: var(--br-text1); margin-bottom: 4px; }
.hint { font-size: 11px; color: var(--br-text3); margin-left: 6px; }
</style>
