<!-- src/components/edit/MasterOutlineEdit.vue -->
<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import {
  NModal, NForm, NFormItem, NInput, NDynamicTags, NSpace, NButton, useMessage,
} from 'naive-ui'
import { api } from '../../api/client'

interface MasterOutline {
  theme_evolution?: string | null
  key_arcs?: string[] | null
  key_milestones?: string[] | null
  rhythm_curve?: string | null
}

const props = defineProps<{
  show: boolean
  wid: string
  master: MasterOutline | null
}>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  saved: []
}>()

const msg = useMessage()
const saving = ref(false)

const form = reactive({
  theme_evolution: '',
  rhythm_curve: '',
  key_arcs: [] as string[],
  key_milestones: [] as string[],
})

let initial: Record<string, any> = {}

function snapshotFromMaster(m: MasterOutline | null) {
  if (!m) {
    Object.assign(form, { theme_evolution: '', rhythm_curve: '', key_arcs: [], key_milestones: [] })
    initial = {}
    return
  }
  form.theme_evolution = m.theme_evolution ?? ''
  form.rhythm_curve = m.rhythm_curve ?? ''
  form.key_arcs = Array.isArray(m.key_arcs) ? [...m.key_arcs] : []
  form.key_milestones = Array.isArray(m.key_milestones) ? [...m.key_milestones] : []
  initial = {
    theme_evolution: form.theme_evolution,
    rhythm_curve: form.rhythm_curve,
    key_arcs: [...form.key_arcs],
    key_milestones: [...form.key_milestones],
  }
}

watch(() => props.master, m => snapshotFromMaster(m), { immediate: true })

const showModel = ref(props.show)
watch(() => props.show, v => { showModel.value = v })
watch(showModel, v => emit('update:show', v))

// diff：仅收集改动字段
function buildChangedFields(): Record<string, any> {
  const changed: Record<string, any> = {}
  if (form.theme_evolution !== initial.theme_evolution) changed.theme_evolution = form.theme_evolution
  if (form.rhythm_curve !== initial.rhythm_curve) changed.rhythm_curve = form.rhythm_curve
  if (JSON.stringify(form.key_arcs) !== JSON.stringify(initial.key_arcs)) changed.key_arcs = [...form.key_arcs]
  if (JSON.stringify(form.key_milestones) !== JSON.stringify(initial.key_milestones)) changed.key_milestones = [...form.key_milestones]
  return changed
}

const isDirty = computed(() => Object.keys(buildChangedFields()).length > 0)

async function save() {
  const changed = buildChangedFields()
  if (!Object.keys(changed).length) {
    msg.info('无改动')
    return
  }
  saving.value = true
  try {
    const r: any = await api.patchMaster(props.wid, changed)
    if (r && r.ok === false) {
      msg.error(r.error || '保存失败')
      return
    }
    msg.success('已保存 master_outline')
    emit('saved')
    showModel.value = false
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}

function cancel() {
  showModel.value = false
}
</script>

<template>
  <NModal v-model:show="showModel" preset="card" style="width:560px;max-width:90vw" title="编辑 master_outline">
    <NForm label-placement="top">
      <NFormItem label="theme_evolution（主题演进）">
        <NInput
          v-model:value="form.theme_evolution"
          type="textarea"
          :rows="3"
          placeholder="主题如何随卷演进"
        />
      </NFormItem>

      <NFormItem label="rhythm_curve（节奏曲线）">
        <NInput
          v-model:value="form.rhythm_curve"
          placeholder="如 缓-急-缓 / 各卷张弛节奏"
        />
      </NFormItem>

      <NFormItem label="key_arcs（关键弧线）">
        <NDynamicTags v-model:value="form.key_arcs" :max="50" />
      </NFormItem>

      <NFormItem label="key_milestones（关键里程碑）">
        <NDynamicTags v-model:value="form.key_milestones" :max="50" />
      </NFormItem>
    </NForm>

    <template #footer>
      <NSpace justify="end" style="width:100%">
        <NButton @click="cancel">取消</NButton>
        <NButton type="primary" :loading="saving" :disabled="!isDirty" @click="save">保存</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
