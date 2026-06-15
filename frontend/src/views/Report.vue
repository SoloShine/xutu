<!-- src/views/Report.vue -->
<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { NSelect, NAlert, NCard, NEmpty, NSpin } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()

interface ReportVol {
  volume_id: number
  exists: boolean
}
interface ReportBody {
  html_body: string
  escalate_chs: number[]
  has_escalate: boolean
}

interface SelectOption {
  label: string
  value: number
}

const volumes = ref<SelectOption[]>([])
const selectedVid = ref<number | null>(null)
const report = ref<ReportBody | null>(null)
const listLoading = ref(true)
const reportLoading = ref(false)
const error = ref('')

async function loadVolumeList() {
  if (!props.wid) {
    listLoading.value = false
    volumes.value = []
    selectedVid.value = null
    return
  }
  listLoading.value = true
  error.value = ''
  try {
    const list = (await api.reports(props.wid)) as ReportVol[]
    const opts = (list || [])
      .filter((v) => v && v.exists)
      .map<SelectOption>((v) => ({ label: '卷' + v.volume_id, value: v.volume_id }))
    volumes.value = opts
    selectedVid.value = opts.length ? opts[0].value : null
  } catch (e: any) {
    error.value = e?.message || String(e)
    volumes.value = []
    selectedVid.value = null
  } finally {
    listLoading.value = false
  }
}

async function loadReport(vid: number) {
  if (!props.wid || vid == null) {
    report.value = null
    return
  }
  reportLoading.value = true
  error.value = ''
  try {
    report.value = (await api.report(props.wid, vid)) as ReportBody
  } catch (e: any) {
    error.value = e?.message || String(e)
    report.value = null
  } finally {
    reportLoading.value = false
  }
}

onMounted(loadVolumeList)
watch(() => props.wid, loadVolumeList)
watch(selectedVid, (vid) => {
  if (vid != null) loadReport(vid)
  else report.value = null
})
</script>

<template>
  <div>
    <h2 style="color:var(--br-text1);margin-top:0">Review 报告</h2>

    <NSpin v-if="listLoading" />

    <template v-else>
      <div v-if="error" style="color:#e06c6c;padding:12px 0">加载失败：{{ error }}</div>

      <!-- 无任何报告 -->
      <NEmpty
        v-else-if="!volumes.length"
        description="该作品无 Review 报告"
        style="padding:40px 0"
      />

      <template v-else>
        <!-- 卷选择 -->
        <div class="vol-bar">
          <NSelect
            v-model:value="selectedVid"
            :options="volumes"
            size="small"
            style="width:200px"
            placeholder="选择卷"
          />
        </div>

        <NSpin v-if="reportLoading" />

        <template v-else-if="report">
          <!-- escalate 警示 -->
          <NAlert
            v-if="report.has_escalate"
            type="warning"
            :show-icon="true"
            style="margin-bottom:16px"
          >
            本卷含 escalate_human 项
            <span v-if="report.escalate_chs && report.escalate_chs.length" class="esc-meta">
              （章节：{{ report.escalate_chs.join(', ') }}）
            </span>
          </NAlert>

          <!-- 报告正文 -->
          <NCard class="report-card" size="small">
            <div class="report-body" v-html="report.html_body"></div>
          </NCard>
        </template>
      </template>
    </template>
  </div>
</template>

<style scoped>
.vol-bar {
  margin-bottom: 16px;
}
.esc-meta {
  color: var(--br-text3);
  margin-left: 4px;
}
.report-card {
  background: var(--br-card);
  border: 1px solid var(--br-border);
  max-width: 820px;
}
:deep(.report-card .n-card__content) {
  color: var(--br-text2);
}
.report-body {
  max-width: 820px;
  line-height: 1.75;
  font-size: 15px;
  color: var(--br-text2);
}
.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3),
.report-body :deep(h4) {
  color: var(--br-text1);
  font-weight: 600;
  margin: 1.2em 0 0.6em;
  line-height: 1.3;
}
.report-body :deep(h1) {
  font-size: 1.5em;
  border-bottom: 1px solid var(--br-border);
  padding-bottom: 0.3em;
}
.report-body :deep(h2) {
  font-size: 1.3em;
}
.report-body :deep(h3) {
  font-size: 1.12em;
}
.report-body :deep(p) {
  margin: 0.6em 0;
}
.report-body :deep(ul),
.report-body :deep(ol) {
  margin: 0.6em 0;
  padding-left: 1.6em;
}
.report-body :deep(li) {
  margin: 0.25em 0;
}
.report-body :deep(code) {
  background: var(--br-border);
  color: var(--br-primary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}
.report-body :deep(pre) {
  background: var(--br-border);
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
}
.report-body :deep(pre code) {
  background: transparent;
  padding: 0;
  color: var(--br-text2);
}
.report-body :deep(strong) {
  color: var(--br-text1);
}
.report-body :deep(a) {
  color: #569cd6;
}
.report-body :deep(blockquote) {
  border-left: 3px solid var(--br-border);
  margin: 0.6em 0;
  padding: 0.2em 0 0.2em 1em;
  color: var(--br-text3);
}
.report-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--br-border);
  margin: 1.2em 0;
}

/* escalate 高亮（服务端注入 class） */
.report-body :deep(.escalate-highlight) {
  border-left: 3px solid #e06c6c;
  background: rgba(224, 108, 108, 0.1);
  padding: 6px 10px;
  margin: 4px 0;
  list-style: none;
  color: var(--br-text1);
}
</style>
