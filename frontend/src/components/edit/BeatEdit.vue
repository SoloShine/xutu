<!-- src/components/edit/BeatEdit.vue -->
<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import {
  NModal, NForm, NFormItem, NInput, NSelect, NSpace, NButton,
  NTooltip, NTag, useMessage,
} from 'naive-ui'
import { api } from '../../api/client'

interface Beat {
  id: number
  sequence: number
  purpose?: string | null
  pov_name?: string | null
  scene_setting?: string | null
  status?: string | null
  deviation_note?: string | null
  volume_id?: number | null
  [k: string]: any
}

const props = defineProps<{
  show: boolean
  wid: string
  beat: Beat | null
  volumeLocked: boolean
}>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  saved: []
}>()

const msg = useMessage()
const saving = ref(false)
const savingContract = ref(false)

const statusOptions = ['planned', 'written', 'verified', 'deviated', 'overridden']
  .map(v => ({ label: v, value: v }))

const form = reactive({
  purpose: '',
  scene_setting: '',
  status: 'planned',
  deviation_note: '',
})

// 初始值快照（用于 diff）
let initial: Record<string, any> = {}

function snapshotFromBeat(b: Beat | null) {
  if (!b) {
    Object.assign(form, { purpose: '', scene_setting: '', status: 'planned', deviation_note: '' })
    initial = {}
    return
  }
  form.purpose = b.purpose ?? ''
  form.scene_setting = b.scene_setting ?? ''
  form.status = b.status ?? 'planned'
  form.deviation_note = b.deviation_note ?? ''
  initial = {
    purpose: form.purpose,
    scene_setting: form.scene_setting,
    status: form.status,
    deviation_note: form.deviation_note,
  }
}

watch(() => props.beat, b => snapshotFromBeat(b), { immediate: true })

// v-model:show 代理
const showModel = ref(props.show)
watch(() => props.show, v => { showModel.value = v })
watch(showModel, v => emit('update:show', v))

// diff：仅收集改动字段
function buildChangedFields(): Record<string, any> {
  const changed: Record<string, any> = {}
  for (const k of ['purpose', 'scene_setting', 'status', 'deviation_note'] as const) {
    if (form[k] !== initial[k]) {
      changed[k] = form[k]
    }
  }
  return changed
}

const isDirty = computed(() => Object.keys(buildChangedFields()).length > 0)

// purpose < 10 字时后端拒（update_beat_meta 要求 ≥10 字）
const purposeTooShort = computed(() => form.purpose.length > 0 && form.purpose.trim().length < 10)

// 仅契约字段（purpose/scene_setting）改动
function buildContractFields(): Record<string, any> {
  const changed: Record<string, any> = {}
  if (form.purpose !== initial.purpose) changed.purpose = form.purpose
  if (form.scene_setting !== initial.scene_setting) changed.scene_setting = form.scene_setting
  return changed
}
const contractDirty = computed(() => Object.keys(buildContractFields()).length > 0)

async function save() {
  if (!props.beat) return
  const changed = buildChangedFields()
  if (!Object.keys(changed).length) {
    msg.info('无改动')
    return
  }
  // 前端预检：purpose 改了但 < 10 字
  if ('purpose' in changed && changed.purpose.trim().length < 10) {
    msg.error('purpose 至少 10 字')
    return
  }
  saving.value = true
  try {
    const r: any = await api.patch(props.wid, 'beats', props.beat.id, changed)
    if (r && r.ok === false) {
      msg.error(r.error || '保存失败')
      return
    }
    msg.success('已保存 beat')
    emit('saved')
    showModel.value = false
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}

// 保存到契约（volume_outline 必须非 locked）
async function saveContract() {
  if (!props.beat || !props.beat.volume_id) {
    msg.error('缺少 volume_id，无法更新契约')
    return
  }
  if (props.volumeLocked) {
    msg.error('卷已锁定，需 CLI unlock')
    return
  }
  const changed = buildContractFields()
  if (!Object.keys(changed).length) {
    msg.info('契约字段无改动')
    return
  }
  if ('purpose' in changed && changed.purpose.trim().length < 10) {
    msg.error('purpose 至少 10 字')
    return
  }
  savingContract.value = true
  try {
    const r: any = await api.patchBeatContract(props.wid, props.beat.volume_id, props.beat.id, changed)
    if (r && r.ok === false) {
      msg.error(r.error || '契约保存失败')
      return
    }
    msg.success('已保存 beat 契约')
    emit('saved')
    showModel.value = false
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    savingContract.value = false
  }
}

function cancel() {
  showModel.value = false
}
</script>

<template>
  <NModal v-model:show="showModel" preset="card" style="width:520px;max-width:90vw" :title="`编辑 beat ${beat?.sequence ?? ''}`">
    <NForm label-placement="top" v-if="beat">
      <NFormItem label="purpose（≥10 字）">
        <NInput
          v-model:value="form.purpose"
          type="textarea"
          :rows="3"
          placeholder="本 beat 的叙事目的，至少 10 字"
        />
        <template #feedback>
          <span v-if="purposeTooShort" style="color:#e06c6c">purpose 不足 10 字，后端会拒绝</span>
        </template>
      </NFormItem>

      <NFormItem label="scene_setting（场景设定，文本或 JSON 字符串）">
        <NInput
          v-model:value="form.scene_setting"
          type="textarea"
          :rows="3"
          placeholder='如 {"location":"大殿","time":"夜"} 或纯文本'
        />
      </NFormItem>

      <NFormItem label="status">
        <NSelect v-model:value="form.status" :options="statusOptions" />
      </NFormItem>

      <NFormItem label="deviation_note（偏差备注）">
        <NInput
          v-model:value="form.deviation_note"
          type="textarea"
          :rows="2"
          placeholder="status=deviated/overridden 时的偏差说明"
        />
      </NFormItem>

      <!-- 卷锁定状态提示 -->
      <div class="lock-box">
        <NTag size="small" :type="volumeLocked ? 'error' : 'default'" :bordered="false" round>
          {{ volumeLocked ? '卷已锁定' : '卷未锁定（可改契约）' }}
        </NTag>
      </div>
    </NForm>

    <template #footer>
      <NSpace justify="space-between" style="width:100%">
        <NButton @click="cancel">取消</NButton>
        <NSpace>
          <!-- 保存到契约：locked → disabled + tooltip -->
          <NTooltip>
            <template #trigger>
              <span>
                <NButton
                  :loading="savingContract"
                  :disabled="volumeLocked || !contractDirty"
                  @click="saveContract"
                >保存到契约</NButton>
              </span>
            </template>
            <span>{{ volumeLocked ? '卷已锁定，需 CLI unlock' : '写入 volume_outline.beat_contracts（purpose/scene_setting）' }}</span>
          </NTooltip>
          <NButton type="primary" :loading="saving" :disabled="!isDirty || purposeTooShort" @click="save">保存</NButton>
        </NSpace>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.lock-box {
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--br-card);
  border: 1px solid var(--br-border);
  border-radius: 6px;
}
</style>
