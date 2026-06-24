<!-- src/views/Chat.vue -->
<!-- AI 工作台:作者助手 agent。对话式创作——agent 读现状+产结构化提案,作者在卡片里审批后才落库。
     agent 用 author process 模型(未绑→全局默认);提案落库经 repo 函数,守铁律。 -->
<script setup lang="ts">
import { ref, watch, computed, nextTick, onUnmounted } from 'vue'
import { NSpin, NEmpty, NCard, NSpace, NInput, NButton, NTag, NPopconfirm, NAlert, useMessage } from 'naive-ui'
import { marked } from 'marked'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()

interface Msg { id: number; role: 'user' | 'assistant' | 'tool'; content: string; ts: string }
interface Proposal { id: number; action_type: string; payload: any; status: string; result: any; created_at: string }

const sessions = ref<{ id: number; title: string; message_count: number; updated_at: string }[]>([])
const sid = ref<number | null>(null)
const messages = ref<Msg[]>([])
const proposals = ref<Proposal[]>([])
const loading = ref(true)
const sending = ref(false)
const input = ref('')
const newTitle = ref('')
const scrollEl = ref<HTMLElement | null>(null)

marked.setOptions({ breaks: true, gfm: true })
function renderMd(text: string): string {
  // agent 回复渲染 markdown(表格/列表/加粗/代码)。本地工具,可信。
  return marked.parse(text || '', { async: false }) as string
}

async function loadSessions() {
  try { sessions.value = await api.chatSessions(props.wid) as any }
  catch (e: any) { msg.error('加载会话失败: ' + (e.message || e)) }
}
async function loadSession() {
  if (sid.value == null) { messages.value = []; proposals.value = []; return }
  try {
    const r = await api.chatGetSession(props.wid, sid.value) as any
    messages.value = r.messages || []
    proposals.value = r.proposals || []
    await scrollBottom()
  } catch (e: any) { msg.error('加载对话失败: ' + (e.message || e)) }
}
async function scrollBottom() {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
}
async function refreshAll() {
  loading.value = true
  await loadSessions()
  await loadSession()
  loading.value = false
}
watch(() => props.wid, refreshAll, { immediate: true })
watch(sid, loadSession)

async function createSession() {
  try {
    const r = await api.chatCreateSession(props.wid, { title: newTitle.value || '' }) as any
    newTitle.value = ''
    await loadSessions()
    sid.value = r.item.id
  } catch (e: any) { msg.error('建会话失败: ' + (e.message || e)) }
}

async function send() {
  const text = input.value.trim()
  if (!text || sid.value == null || sending.value) return
  sending.value = true
  input.value = ''
  // 乐观渲染:立即把用户消息显示出来(负 id 占位,响应回来用服务端版本替换)
  messages.value.push({ id: -Date.now(), role: 'user', content: text, ts: '' })
  await scrollBottom()
  try {
    const r = await api.chatSend(props.wid, sid.value, text) as any
    if (r && r.messages) { messages.value = r.messages; proposals.value = r.proposals || [] }
    else { msg.error('agent 执行失败: ' + ((r as any)?.error || '')); await loadSession() }
    await scrollBottom()
  } catch (e: any) { msg.error('发送失败: ' + (e.message || e)) }
  finally { sending.value = false }
}

async function decide(p: Proposal, approved: boolean) {
  try {
    const r = await api.chatDecide(props.wid, p.id, approved) as any
    const it = r.item
    const idx = proposals.value.findIndex(x => x.id === p.id)
    if (idx >= 0) proposals.value[idx] = it
    if (it.status === 'approved' && it.result?.error) msg.error('执行失败: ' + it.result.error)
    else if (it.status === 'approved') msg.success(`提案 #${p.id} 已执行:${p.action_type}`)
    else msg.info(`提案 #${p.id} 已驳回`)
    if (it.status === 'approved' && !it.result?.error) await loadSessions()
  } catch (e: any) { msg.error('审批失败: ' + (e.message || e)) }
}

function proposalBadge(p: Proposal): 'info' | 'success' | 'warning' | 'error' {
  return p.status === 'pending' ? 'warning' : p.status === 'approved' ? 'success' : 'error'
}
function ppayload(p: Proposal): string {
  return Object.entries(p.payload || {}).map(([k, v]) =>
    typeof v === 'object' ? `${k}: ${JSON.stringify(v)}` : `${k}: ${v}`).join(' · ')
}
</script>

<template>
  <div class="chat-wrap">
    <NSpin :show="loading" style="height:100%">
      <div class="chat-inner">
        <NAlert type="info" class="chat-header" :show-icon="true">
          <strong>AI 工作台</strong> — 作者助手帮你做写前创作(规划章节/起草 beat/查设定)。agent 读现状后产<strong>提案</strong>,
          你在卡片里点「接受」才落库经 repo(守铁律)。模型 = author process(未绑用全局默认)。
        </NAlert>

        <div class="chat-layout">
          <!-- 左:会话列表 -->
          <NCard size="small" class="sess-card" :content-style="{ background: 'var(--br-card)', padding: '10px', height: '100%', overflow: 'hidden' }">
            <div style="margin-bottom:8px">
              <NInput v-model:value="newTitle" size="small" placeholder="新会话标题" @keyup.enter="createSession" />
              <NButton size="small" type="primary" block style="margin-top:6px" @click="createSession">+ 新会话</NButton>
            </div>
            <div class="sess-list">
              <NEmpty v-if="!sessions.length" description="暂无会话" size="small" />
              <div v-for="s in sessions" :key="s.id" class="sess-item" :class="{ active: s.id === sid }" @click="sid = s.id">
                <div class="sess-title">{{ s.title || ('#' + s.id) }}</div>
                <div class="sess-meta">{{ s.message_count }} 条 · {{ (s.updated_at || '').slice(5, 16) }}</div>
              </div>
            </div>
          </NCard>

          <!-- 右:消息 + 提案 + 输入 -->
          <div class="chat-main">
            <NCard size="small" class="msg-card" :content-style="{ background: 'var(--br-card)', padding: '12px', display: 'flex', flexDirection: 'column', minHeight: '0', flex: '1' }">
              <div ref="scrollEl" class="msg-stream">
                <NEmpty v-if="!messages.length" description="发一句话开始(如:帮我起草第25章的 beat 契约)" size="small" />
                <div v-for="m in messages" :key="m.id" class="msg-row" :class="m.role">
                  <NTag size="tiny" :type="m.role === 'user' ? 'info' : m.role === 'tool' ? 'warning' : 'success'"
                        :bordered="false" class="msg-role">{{ m.role }}</NTag>
                  <div v-if="m.role === 'assistant'" class="msg-text md" v-html="renderMd(m.content)"></div>
                  <div v-else class="msg-text" style="white-space: pre-wrap">{{ m.content }}</div>
                </div>
              </div>
            </NCard>

            <!-- 待审批提案 -->
            <NCard v-if="proposals.some(p => p.status === 'pending')" title="待审批提案" size="small"
                   class="prop-card" :content-style="{ background: 'var(--br-card)', padding: '8px 12px' }">
              <div v-for="p in proposals.filter(x => x.status === 'pending')" :key="p.id" class="prop-row">
                <NTag size="tiny" :type="proposalBadge(p)" :bordered="false">{{ p.action_type }}</NTag>
                <span class="prop-payload">{{ ppayload(p) }}</span>
                <NSpace :size="6">
                  <NButton size="tiny" type="primary" @click="decide(p, true)">接受并落库</NButton>
                  <NPopconfirm @positive-click="decide(p, false)"><template #trigger>
                    <NButton size="tiny" ghost>驳回</NButton>
                  </template>驳回提案 #{{ p.id }}?</NPopconfirm>
                </NSpace>
              </div>
            </NCard>

            <NCard v-if="proposals.some(p => p.status !== 'pending')" title="历史提案" size="small"
                   class="prop-card" :content-style="{ background: 'var(--br-card)', padding: '8px 12px' }">
              <div v-for="p in proposals.filter(x => x.status !== 'pending')" :key="p.id" class="prop-row hist">
                <NTag size="tiny" :type="proposalBadge(p)" :bordered="false">{{ p.status }}</NTag>
                <NTag size="tiny" :bordered="false">{{ p.action_type }}</NTag>
                <span class="prop-payload">{{ ppayload(p) }}</span>
                <span class="prop-result">{{ p.result?.error ? '✗ ' + p.result.error : '✓ 已执行' }}</span>
              </div>
            </NCard>

            <!-- 输入 -->
            <div class="input-row">
              <NInput v-model:value="input" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }" class="input-box"
                      placeholder="对作者助手说(如:续写第25章,韩峥与林深摊牌)..." :disabled="sid == null"
                      @keydown.enter.exact.prevent="send" />
              <NButton type="primary" size="large" :loading="sending" :disabled="!input.trim() || sid == null" @click="send">发送</NButton>
            </div>
            <div class="hint">Enter 发送(Shift+Enter 换行)。agent 会读现状→产提案,你审批后才落库。</div>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.chat-wrap { height: 100%; min-height: 0; }
.chat-wrap :deep(.n-spin-container) { height: 100%; }
.chat-wrap :deep(.n-spin-content) { height: 100%; }
.chat-inner { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.chat-header { flex-shrink: 0; margin-bottom: 10px; }
.chat-layout { flex: 1; min-height: 0; display: grid; grid-template-columns: 240px 1fr; gap: 12px; }
/* 左:会话卡铺满,内部滚动 */
.sess-card { display: flex; flex-direction: column; min-height: 0; }
.sess-card :deep(.n-card__content) { display: flex; flex-direction: column; min-height: 0; }
.sess-list { flex: 1; min-height: 0; overflow-y: auto; }
.sess-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; border: 1px solid var(--br-border-soft); margin-bottom: 6px; }
.sess-item:hover { background: var(--br-elevated, var(--br-sider)); }
.sess-item.active { border-color: var(--br-primary); background: var(--br-elevated, var(--br-sider)); }
.sess-title { font-weight: 600; color: var(--br-text1); font-size: 13px; }
.sess-meta { font-size: 11px; color: var(--br-text3); margin-top: 2px; }
/* 右:主区铺满 */
.chat-main { display: flex; flex-direction: column; gap: 10px; min-height: 0; height: 100%; }
.msg-card { min-height: 0; }
.msg-stream { flex: 1; min-height: 0; overflow-y: auto; padding-right: 4px; }
.msg-row { display: flex; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--br-border-soft); }
.msg-row.user { background: color-mix(in srgb, var(--br-primary) 6%, transparent); border-radius: 6px; padding: 8px 6px; }
.msg-role { flex-shrink: 0; margin-top: 2px; }
.msg-text { font-size: 13px; color: var(--br-text1); line-height: 1.65; flex: 1; min-width: 0; }
/* 待审批/历史提案卡不挤压消息区 */
.prop-card { flex-shrink: 0; }
.prop-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--br-border-soft); }
.prop-row.hist { font-size: 12px; }
.prop-payload { flex: 1; font-family: monospace; font-size: 12px; color: var(--br-text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prop-result { font-size: 11px; color: var(--br-text3); }
/* 输入行:输入框撑满,按钮固定 */
.input-row { display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0; }
.input-box { flex: 1; }
.hint { font-size: 11px; color: var(--br-text3); flex-shrink: 0; }
</style>

<!-- markdown 渲染样式(非 scoped,穿透 v-html) -->
<style>
.msg-text.md h1, .msg-text.md h2, .msg-text.md h3 { margin: 0.5em 0 0.3em; font-size: 15px; }
.msg-text.md p { margin: 0.3em 0; }
.msg-text.md ul, .msg-text.md ol { margin: 0.3em 0; padding-left: 1.4em; }
.msg-text.md li { margin: 0.15em 0; }
.msg-text.md table { border-collapse: collapse; margin: 0.4em 0; font-size: 12px; }
.msg-text.md th, .msg-text.md td { border: 1px solid var(--br-border); padding: 3px 8px; text-align: left; }
.msg-text.md th { background: var(--br-elevated, var(--br-sider)); }
.msg-text.md code { background: var(--br-elevated, var(--br-sider)); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.msg-text.md pre { background: var(--br-elevated, var(--br-sider)); padding: 8px; border-radius: 4px; overflow-x: auto; }
.msg-text.md blockquote { border-left: 3px solid var(--br-primary); margin: 0.4em 0; padding-left: 10px; color: var(--br-text2); }
.msg-text.md strong { color: var(--br-text1); }
</style>
