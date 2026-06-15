<!-- src/components/edit/WorldbookInline.vue -->
<!-- 总览世界观三组内联编辑：locations(按id) / themes(按name) / motifs(按name) -->
<script setup lang="ts">
import { ref } from 'vue'
import {
  NCard, NCollapse, NCollapseItem, NEmpty, NTag, NInput, NButton, NSpace, useMessage,
} from 'naive-ui'
import { api } from '../../api/client'

interface Location { id: number; name: string; loc_type: string; description: string; state: string }
interface Theme { name: string; description: string; evolution: string }
interface Motif { name: string; meaning: string; evolution: string }
interface Worldbook { locations: Location[]; themes: Theme[]; motifs: Motif[] }

const props = defineProps<{ wid: string; worldbook: Worldbook }>()
const emit = defineEmits<{ updated: [] }>()
const msg = useMessage()

// 编辑态：记录哪条记录的哪个字段正在编辑。
// key 形式：location 描述用 'L:<id>:<field>'；theme/motif 用 'T:<name>:<field>' / 'M:<name>:<field>'
const editing = ref<string | null>(null)
const draft = ref<string>('')
const saving = ref(false)

function startEdit(key: string, current: string) {
  editing.value = key
  draft.value = current || ''
}
function cancelEdit() {
  editing.value = null
  draft.value = ''
}

async function saveLocation(loc: Location, field: 'description') {
  if (!props.wid) return
  saving.value = true
  try {
    const body: any = {}
    body[field] = draft.value
    const res = await api.patch(props.wid, 'locations', loc.id, body)
    if (res && res.ok === false) { msg.error(res.error || '保存失败'); return }
    msg.success('已保存地点')
    loc[field] = draft.value
    editing.value = null
    emit('updated')
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}

async function saveTheme(th: Theme, field: 'description' | 'evolution') {
  if (!props.wid) return
  saving.value = true
  try {
    const res = await api.patch(props.wid, 'themes', th.name, { [field]: draft.value })
    if (res && res.ok === false) { msg.error(res.error || '保存失败'); return }
    msg.success('已保存主题')
    th[field] = draft.value
    editing.value = null
    emit('updated')
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}

async function saveMotif(mo: Motif, field: 'meaning' | 'evolution') {
  if (!props.wid) return
  saving.value = true
  try {
    const res = await api.patch(props.wid, 'motifs', mo.name, { [field]: draft.value })
    if (res && res.ok === false) { msg.error(res.error || '保存失败'); return }
    msg.success('已保存母题')
    mo[field] = draft.value
    editing.value = null
    emit('updated')
  } catch (e: any) {
    msg.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <NCollapse :default-expanded-names="['locations', 'themes', 'motifs']">
    <NCollapseItem title="地点 / Locations" name="locations">
      <NEmpty v-if="!worldbook.locations.length" description="无地点" />
      <div v-else class="wb-list">
        <div v-for="loc in worldbook.locations" :key="loc.id" class="wb-row">
          <div class="wb-row-head">
            <span class="wb-name">{{ loc.name }}</span>
            <NTag v-if="loc.loc_type" size="tiny" type="info" :bordered="false">{{ loc.loc_type }}</NTag>
            <NTag v-if="loc.state" size="tiny" :bordered="false">{{ loc.state }}</NTag>
          </div>
          <!-- description 内联编辑 -->
          <div v-if="editing === `L:${loc.id}:description`" class="wb-edit">
            <NInput
              v-model:value="draft"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="地点描述"
            />
            <NSpace :size="6">
              <NButton size="tiny" type="primary" :loading="saving" @click="saveLocation(loc, 'description')">保存</NButton>
              <NButton size="tiny" @click="cancelEdit">取消</NButton>
            </NSpace>
          </div>
          <div v-else class="wb-display">
            <p v-if="loc.description" class="wb-desc">{{ loc.description }}</p>
            <p v-else class="wb-desc wb-empty">（无描述）</p>
            <NButton size="tiny" quaternary class="wb-edit-btn" @click="startEdit(`L:${loc.id}:description`, loc.description)">编辑描述</NButton>
          </div>
        </div>
      </div>
    </NCollapseItem>

    <NCollapseItem title="主题 / Themes" name="themes">
      <NEmpty v-if="!worldbook.themes.length" description="无主题" />
      <div v-else class="wb-list">
        <div v-for="th in worldbook.themes" :key="th.name" class="wb-row">
          <div class="wb-row-head">
            <span class="wb-name">{{ th.name }}</span>
          </div>
          <!-- description -->
          <div v-if="editing === `T:${th.name}:description`" class="wb-edit">
            <NInput v-model:value="draft" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" placeholder="主题描述" />
            <NSpace :size="6">
              <NButton size="tiny" type="primary" :loading="saving" @click="saveTheme(th, 'description')">保存</NButton>
              <NButton size="tiny" @click="cancelEdit">取消</NButton>
            </NSpace>
          </div>
          <div v-else class="wb-display">
            <p v-if="th.description" class="wb-desc">{{ th.description }}</p>
            <p v-else class="wb-desc wb-empty">（无描述）</p>
            <NButton size="tiny" quaternary class="wb-edit-btn" @click="startEdit(`T:${th.name}:description`, th.description)">编辑描述</NButton>
          </div>
          <!-- evolution -->
          <div v-if="editing === `T:${th.name}:evolution`" class="wb-edit">
            <NInput v-model:value="draft" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="主题演进" />
            <NSpace :size="6">
              <NButton size="tiny" type="primary" :loading="saving" @click="saveTheme(th, 'evolution')">保存</NButton>
              <NButton size="tiny" @click="cancelEdit">取消</NButton>
            </NSpace>
          </div>
          <div v-else class="wb-display">
            <p v-if="th.evolution" class="wb-evol">演进：{{ th.evolution }}</p>
            <NButton size="tiny" quaternary class="wb-edit-btn" @click="startEdit(`T:${th.name}:evolution`, th.evolution)">编辑演进</NButton>
          </div>
        </div>
      </div>
    </NCollapseItem>

    <NCollapseItem title="母题 / Motifs" name="motifs">
      <NEmpty v-if="!worldbook.motifs.length" description="无母题" />
      <div v-else class="wb-list">
        <div v-for="mo in worldbook.motifs" :key="mo.name" class="wb-row">
          <div class="wb-row-head">
            <span class="wb-name">{{ mo.name }}</span>
          </div>
          <!-- meaning -->
          <div v-if="editing === `M:${mo.name}:meaning`" class="wb-edit">
            <NInput v-model:value="draft" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" placeholder="母题含义" />
            <NSpace :size="6">
              <NButton size="tiny" type="primary" :loading="saving" @click="saveMotif(mo, 'meaning')">保存</NButton>
              <NButton size="tiny" @click="cancelEdit">取消</NButton>
            </NSpace>
          </div>
          <div v-else class="wb-display">
            <p v-if="mo.meaning" class="wb-desc">{{ mo.meaning }}</p>
            <p v-else class="wb-desc wb-empty">（无含义）</p>
            <NButton size="tiny" quaternary class="wb-edit-btn" @click="startEdit(`M:${mo.name}:meaning`, mo.meaning)">编辑含义</NButton>
          </div>
          <!-- evolution -->
          <div v-if="editing === `M:${mo.name}:evolution`" class="wb-edit">
            <NInput v-model:value="draft" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="母题演进" />
            <NSpace :size="6">
              <NButton size="tiny" type="primary" :loading="saving" @click="saveMotif(mo, 'evolution')">保存</NButton>
              <NButton size="tiny" @click="cancelEdit">取消</NButton>
            </NSpace>
          </div>
          <div v-else class="wb-display">
            <p v-if="mo.evolution" class="wb-evol">演进：{{ mo.evolution }}</p>
            <NButton size="tiny" quaternary class="wb-edit-btn" @click="startEdit(`M:${mo.name}:evolution`, mo.evolution)">编辑演进</NButton>
          </div>
        </div>
      </div>
    </NCollapseItem>
  </NCollapse>
</template>

<style scoped>
.wb-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wb-row {
  padding: 8px 10px;
  background: #15171c;
  border-radius: 4px;
}
.wb-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.wb-name {
  color: #e6e9ef;
  font-weight: 600;
}
.wb-display {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.wb-display .wb-desc,
.wb-display .wb-evol {
  flex: 1 1 auto;
}
.wb-desc {
  margin: 0;
  color: #b8bfd0;
  font-size: 13px;
  line-height: 1.6;
}
.wb-evol {
  margin: 0;
  color: #7c8494;
  font-size: 12px;
}
.wb-empty {
  color: #5a6070;
  font-style: italic;
}
.wb-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}
.wb-edit-btn {
  flex: 0 0 auto;
  color: #4ec9b0;
}
</style>
