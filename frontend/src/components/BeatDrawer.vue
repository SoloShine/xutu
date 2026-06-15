<!-- src/components/BeatDrawer.vue -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NSpin, NEmpty, NTag } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{
  show: boolean
  wid: string
  chapter: number | null
  character: number | null
  characterName: string
}>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()

interface Beat {
  sequence: number
  purpose: string | null
  status: string | null
  deviation_note: string | null
}

const beats = ref<Beat[]>([])
const loading = ref(false)
const error = ref('')
const chapterTitle = ref('')

const statusTypeMap: Record<string, 'success' | 'info' | 'warning' | 'error' | 'default'> = {
  written: 'success',
  deviated: 'warning',
  overridden: 'info',
  unwritten: 'default',
  missing: 'error',
}
function statusType(s: string | null) {
  return (s && statusTypeMap[s]) || 'default'
}

async function load() {
  if (!props.show || !props.wid || props.chapter == null || props.character == null) return
  loading.value = true
  error.value = ''
  beats.value = []
  try {
    beats.value = (await api.matrixBeats(props.wid, props.chapter, props.character)) as Beat[]
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

watch(() => [props.show, props.chapter, props.character], load, { immediate: true })

const showModel = ref(props.show)
watch(() => props.show, v => { showModel.value = v })
watch(showModel, v => emit('update:show', v))
</script>

<template>
  <NDrawer v-model:show="showModel" :width="480" placement="right">
    <NDrawerContent title="Beat 明细" :native-scrollbar="false">
      <template #header>
        <span style="color:var(--br-text1)">Beat 明细</span>
        <small style="color:var(--br-text3);font-size:12px;margin-left:8px">{{ characterName }}</small>
      </template>

      <NSpin v-if="loading" />
      <div v-else-if="error" style="color:#e06c6c;padding:8px">加载失败：{{ error }}</div>
      <NEmpty v-else-if="!beats.length" description="该角色在此章无 beat" />
      <div v-else class="beat-list">
        <div v-for="b in beats" :key="b.sequence" class="beat-card">
          <div class="beat-head">
            <span class="beat-seq">#{{ b.sequence }}</span>
            <NTag size="small" :type="statusType(b.status)" :bordered="false">
              {{ b.status || '—' }}
            </NTag>
          </div>
          <div class="beat-purpose">{{ b.purpose || '（无 purpose）' }}</div>
          <div v-if="b.deviation_note" class="beat-deviation">
            <span class="dev-label">偏差：</span>{{ b.deviation_note }}
          </div>
        </div>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.beat-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.beat-card {
  background: var(--br-card);
  border: 1px solid var(--br-border);
  border-radius: 6px;
  padding: 12px;
}
.beat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.beat-seq {
  color: var(--br-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.beat-purpose {
  color: var(--br-text1);
  font-size: 14px;
  line-height: 1.6;
}
.beat-deviation {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--br-border);
  color: #e06c6c;
  font-size: 13px;
  line-height: 1.5;
}
.dev-label {
  color: var(--br-text3);
  font-weight: 600;
}
</style>
