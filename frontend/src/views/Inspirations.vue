<!-- src/views/Inspirations.vue -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage, NCard, NTag, NSelect, NButton, NModal, NInput, NSpace, NEmpty, NSpin } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()
const items = ref<any[]>([])
const loading = ref(true)
const typeF = ref<string | null>(null)
const statusF = ref<string | null>(null)
const editing = ref<any | null>(null)
const editContent = ref('')
const editSource = ref('')

const typeOpts = ['premise','scene','character','theme','mechanic','setting','twist'].map(t => ({ label: t, value: t }))
const statusOpts = ['raw','refined','consumed','partial','discarded'].map(s => ({ label: s, value: s }))
const statusColor: Record<string, 'default'|'info'|'success'|'warning'|'error'> = { raw:'default', refined:'info', consumed:'success', partial:'warning', discarded:'error' }

async function load() {
  loading.value = true
  try { items.value = await api.inspirations(props.wid, typeF.value || undefined, statusF.value || undefined) }
  catch (e:any) { msg.error(e.message) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })

const TRANSITIONS: Record<string, string[]> = {
  raw: ['refined','consumed','discarded'],
  refined: ['consumed','partial','discarded'],
  partial: ['consumed','discarded'],
  consumed: ['discarded'],
  discarded: [],
}
const editable = (it: any) => ['raw','refined','partial'].includes(it.status) && (!it.consumed_into || it.consumed_into.length === 0)

async function advance(it: any, target: string) {
  try {
    const r = await api.advance(props.wid, it.id, target)
    if (r.ok) { Object.assign(it, r.item); msg.success(`→ ${target}`) }
    else msg.error(r.error)
  } catch (e:any) { msg.error(e.message) }
}
function openEdit(it: any) { editing.value = it; editContent.value = it.content; editSource.value = it.source || '' }
async function saveEdit() {
  try {
    const r = await api.editInspiration(props.wid, editing.value.id, { content: editContent.value, source: editSource.value })
    if (r.ok) { Object.assign(editing.value, r.item); msg.success('已保存') }
    else msg.error(r.error)
  } catch (e:any) { msg.error(e.message) }
  editing.value = null
}
</script>

<template>
  <h2 style="color:var(--br-text1)">灵感池 <small style="color:var(--br-text3);font-size:13px">{{ items.length }} 条</small></h2>
  <NSpace style="margin-bottom:16px">
    <NSelect v-model:value="typeF" :options="typeOpts" placeholder="类型" clearable style="width:140px" @update:value="load"/>
    <NSelect v-model:value="statusF" :options="statusOpts" placeholder="状态" clearable style="width:140px" @update:value="load"/>
  </NSpace>
  <NSpin v-if="loading"/>
  <NEmpty v-else-if="!items.length" description="无匹配灵感"/>
  <div v-else style="display:flex;flex-direction:column;gap:10px">
    <NCard v-for="it in items" :key="it.id" size="small" :style="{ opacity: it.status==='discarded'?.6:1 }">
      <NSpace align="center" style="margin-bottom:6px">
        <NTag size="small" round type="default">{{ it.type }}</NTag>
        <NTag size="small" round :type="statusColor[it.status]">{{ it.status }}</NTag>
        <NButton v-if="editable(it)" size="tiny" quaternary @click="openEdit(it)">编辑</NButton>
      </NSpace>
      <p style="margin:4px 0;color:var(--br-text1)">{{ it.content }}</p>
      <small style="color:var(--br-text3)">{{ it.source }}</small>
      <div v-if="it.consumed_into?.length" style="margin-top:4px">
        <NTag v-for="(c,i) in it.consumed_into" :key="i" size="tiny" type="success">{{ c.target_type }}#{{ c.target_id }}</NTag>
      </div>
      <NSpace style="margin-top:8px">
        <NButton v-for="t in TRANSITIONS[it.status]" :key="t" size="small" :type="t==='discarded'?'error':'default'"
                 @click="advance(it, t)">→ {{ t }}</NButton>
      </NSpace>
    </NCard>
  </div>

  <NModal v-model:show="editing" preset="card" title="编辑灵感" style="max-width:560px">
    <NInput v-model:value="editContent" type="textarea" :rows="5"/>
    <NInput v-model:value="editSource" placeholder="来源" style="margin-top:8px"/>
    <template #footer><NSpace justify="end"><NButton @click="editing=null">取消</NButton><NButton type="primary" @click="saveEdit">保存</NButton></NSpace></template>
  </NModal>
</template>
