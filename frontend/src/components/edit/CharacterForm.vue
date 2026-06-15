<!-- src/components/edit/CharacterForm.vue -->
<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import {
  NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect,
  NDynamicTags, NSpace, NButton, NTag, useMessage,
} from 'naive-ui'
import { api } from '../../api/client'

interface Character {
  id: number
  name: string
  pronoun: string | null
  gender: string | null
  role: string
  faction_id: number | null
  state: string
  personality: string | null
  goals: string | null
  abilities: string[]
  aliases: string[]
  secret_count: number
  knowledge_count: number
  [k: string]: any
}

const props = defineProps<{
  show: boolean
  wid: string
  character: Character | null
}>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  saved: [item: any]
}>()

const msg = useMessage()
const saving = ref(false)
const factionsLoading = ref(false)

const pronounOptions = ['他', '她', '它', '祂', 'TA'].map(v => ({ label: v, value: v }))
const genderOptions = [
  { label: '（空）', value: '' },
  ...['男', '女', '无', '未知', '其他'].map(v => ({ label: v, value: v })),
]
const roleOptions = ['protagonist', 'supporting', 'antagonist', 'minor'].map(v => ({ label: v, value: v }))
const stateOptions = ['active', 'dormant', 'deceased', 'ascended', 'merged'].map(v => ({ label: v, value: v }))

interface FactionOption { label: string; value: number }
const factionOptions = ref<FactionOption[]>([])

// 表单字段（深拷贝避免直接改父对象）
const form = reactive({
  name: '',
  pronoun: '' as string,
  gender: '' as string,
  role: '' as string,
  state: '' as string,
  faction_id: null as number | null,
  personality: '',
  goals: '',
  abilities: [] as string[],
  aliases: [] as string[],
})

// 初始值快照（用于 diff）
let initial: Record<string, any> = {}

function snapshotFromCharacter(c: Character | null) {
  if (!c) {
    Object.assign(form, {
      name: '', pronoun: '', gender: '', role: '', state: '',
      faction_id: null, personality: '', goals: '',
      abilities: [], aliases: [],
    })
    initial = {}
    return
  }
  form.name = c.name ?? ''
  form.pronoun = c.pronoun ?? ''
  form.gender = c.gender ?? ''
  form.role = c.role ?? ''
  form.state = c.state ?? ''
  form.faction_id = c.faction_id ?? null
  form.personality = c.personality ?? ''
  form.goals = c.goals ?? ''
  form.abilities = Array.isArray(c.abilities) ? [...c.abilities] : []
  form.aliases = Array.isArray(c.aliases) ? [...c.aliases] : []
  initial = {
    name: form.name,
    pronoun: form.pronoun,
    gender: form.gender,
    role: form.role,
    state: form.state,
    faction_id: form.faction_id,
    personality: form.personality,
    goals: form.goals,
    abilities: [...form.abilities],
    aliases: [...form.aliases],
  }
}

watch(() => props.character, c => snapshotFromCharacter(c), { immediate: true })

// v-model:show 代理
const showModel = ref(props.show)
watch(() => props.show, v => { showModel.value = v })
watch(showModel, v => emit('update:show', v))

// faction 选项加载
watch(() => [props.show, props.wid], async ([s, wid]) => {
  if (!s || !wid) return
  if (factionOptions.value.length) return
  factionsLoading.value = true
  try {
    const list = (await api.factions(wid as string)) as any[]
    factionOptions.value = list.map(f => ({ label: f.name ?? String(f.id), value: f.id }))
  } catch {
    factionOptions.value = []
  } finally {
    factionsLoading.value = false
  }
}, { immediate: true })

const isDirty = computed(() => {
  if (!props.character) return false
  for (const k of Object.keys(initial)) {
    const a = (form as any)[k]
    const b = initial[k]
    if (Array.isArray(a) || Array.isArray(b)) {
      if (JSON.stringify(a ?? []) !== JSON.stringify(b ?? [])) return true
    } else if (a !== b) {
      return true
    }
  }
  return false
})

// diff：仅收集改动字段（select 空串 → 后端期望 null/清空）
function buildChangedFields(): Record<string, any> {
  const changed: Record<string, any> = {}
  const fields = ['name', 'pronoun', 'gender', 'role', 'state', 'faction_id', 'personality', 'goals']
  for (const k of fields) {
    const a = (form as any)[k]
    const b = initial[k]
    if (a !== b) {
      // 空 select 归一化为 null（除 name 外）
      if (k !== 'name' && a === '') changed[k] = null
      else changed[k] = a
    }
  }
  // 列表字段：JSON 比对，改动则整体发数组
  if (JSON.stringify(form.abilities) !== JSON.stringify(initial.abilities)) {
    changed.abilities = [...form.abilities]
  }
  if (JSON.stringify(form.aliases) !== JSON.stringify(initial.aliases)) {
    changed.aliases = [...form.aliases]
  }
  return changed
}

async function save() {
  if (!props.character) return
  const changed = buildChangedFields()
  if (!Object.keys(changed).length) {
    msg.info('无改动')
    return
  }
  saving.value = true
  try {
    const r: any = await api.patch(props.wid, 'characters', props.character.id, changed)
    if (r && r.ok === false) {
      msg.error(r.error || '保存失败')
      return
    }
    msg.success('已保存')
    const item = r?.item ?? r
    emit('saved', item)
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
  <NDrawer v-model:show="showModel" :width="600" placement="right">
    <NDrawerContent title="编辑角色" :native-scrollbar="false" closable>
      <template #header>
        <span style="color:#e6e9ef">编辑角色</span>
        <small style="color:#7c8494;font-size:12px;margin-left:8px">{{ character?.name }}</small>
      </template>

      <NForm label-placement="top" v-if="character">
        <NSpace>
          <NFormItem label="姓名" style="flex:1">
            <NInput v-model:value="form.name" placeholder="姓名" />
          </NFormItem>
          <NFormItem label="代词" style="width:120px">
            <NSelect v-model:value="form.pronoun" :options="pronounOptions" clearable placeholder="代词" />
          </NFormItem>
        </NSpace>

        <NSpace>
          <NFormItem label="gender" style="flex:1">
            <NSelect v-model:value="form.gender" :options="genderOptions" placeholder="gender" />
          </NFormItem>
          <NFormItem label="role" style="flex:1">
            <NSelect v-model:value="form.role" :options="roleOptions" placeholder="role" />
          </NFormItem>
          <NFormItem label="state" style="flex:1">
            <NSelect v-model:value="form.state" :options="stateOptions" placeholder="state" />
          </NFormItem>
        </NSpace>

        <NFormItem label="派系">
          <NSelect
            v-model:value="form.faction_id"
            :options="factionOptions"
            :loading="factionsLoading"
            clearable
            placeholder="派系（可清空）"
          />
        </NFormItem>

        <NFormItem label="性格">
          <NInput v-model:value="form.personality" type="textarea" :rows="3" placeholder="性格" />
        </NFormItem>

        <NFormItem label="目标">
          <NInput v-model:value="form.goals" type="textarea" :rows="3" placeholder="目标" />
        </NFormItem>

        <NFormItem label="能力 (abilities)">
          <NDynamicTags v-model:value="form.abilities" :max="50" />
        </NFormItem>

        <NFormItem label="别名 (aliases)">
          <NDynamicTags v-model:value="form.aliases" :max="50" />
        </NFormItem>

        <!-- secrets / knowledge 只读 -->
        <div class="readonly-box">
          <div class="ro-head">
            <span class="ro-title">secrets / knowledge</span>
            <NTag size="small" :bordered="false" type="warning">v1 暂不可编辑</NTag>
          </div>
          <div class="ro-counts">
            <span>secrets: <b>{{ character.secret_count ?? 0 }}</b></span>
            <span>knowledge: <b>{{ character.knowledge_count ?? 0 }}</b></span>
          </div>
        </div>
      </NForm>

      <template #footer>
        <NSpace>
          <NButton @click="cancel">取消</NButton>
          <NButton type="primary" :loading="saving" :disabled="!isDirty" @click="save">保存</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.readonly-box {
  margin-top: 12px;
  padding: 12px;
  background: #1a1d24;
  border: 1px solid #2a2e38;
  border-radius: 6px;
}
.ro-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ro-title {
  color: #4ec9b0;
  font-weight: 600;
}
.ro-counts {
  color: #b8bfd0;
  font-size: 13px;
  display: flex;
  gap: 24px;
}
.ro-counts b {
  color: #e6e9ef;
  font-variant-numeric: tabular-nums;
}
</style>
