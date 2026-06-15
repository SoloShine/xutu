<!-- src/components/PanelWorkspace.vue -->
<!-- 分屏工作站主区：顶部工具栏（布局预设 + 命名布局 + 右分屏/下分行）+ 主体（Splitpanes 行×列嵌套；
     最大化时只渲染单个面板撑满）。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NButtonGroup, NSelect, NPopover, NInput, NEmpty, useMessage } from 'naive-ui'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import PanelPane from './PanelPane.vue'
import { usePanels, type Panel } from '../stores/panels'

defineProps<{ wid: string }>()
const panels = usePanels()
const msg = useMessage()

const presetName = computed(() => {
  const r = panels.rows
  const n = r.reduce((s, row) => s + row.length, 0)
  if (n === 1) return 'single'
  if (r.length === 1 && r[0].length === 2) return 'dual'
  if (r.length === 1 && r[0].length === 3) return 'triple'
  if (r.length === 2 && r[0].length === 2 && r[1].length === 2) return 'grid'
  return ''
})

const presetSeg = [
  { label: '单', value: 'single' },
  { label: '双', value: 'dual' },
  { label: '三', value: 'triple' },
  { label: '2×2', value: 'grid' },
] as const

// 命名布局下拉选项
const layoutOptions = computed(() => panels.layoutNames.map(n => ({ label: n, value: n })))
function onApplyLayout(name: string | null) {
  if (name && panels.applyLayout(name)) msg.success(`已载入布局「${name}」`)
}
// 存为弹层
const saveShow = ref(false)
const saveName = ref('')
function doSave() {
  const n = saveName.value.trim()
  if (!n) { msg.warning('请输入布局名'); return }
  const existed = !!panels.namedLayouts[n]
  panels.saveLayout(n)
  msg.success(existed ? `已覆盖布局「${n}」` : `已保存布局「${n}」`)
  saveName.value = ''
  saveShow.value = false
}
function doDelete(name: string) {
  panels.deleteLayout(name)
  msg.success(`已删除布局「${name}」`)
}

// 最大化：找到当前最大化面板
const maxPanel = computed<Panel | null>(() => {
  if (panels.maximizedId === null) return null
  for (const row of panels.rows) {
    const p = row.find(x => x.id === panels.maximizedId)
    if (p) return p
  }
  return null
})
</script>

<template>
  <div class="ws-root">
    <!-- 紧凑工具栏 -->
    <div class="ws-bar">
      <NButtonGroup size="tiny">
        <NButton
          v-for="p in presetSeg" :key="p.value"
          :type="presetName === p.value ? 'primary' : 'default'"
          @click="panels.applyPreset(p.value)"
        >{{ p.label }}</NButton>
      </NButtonGroup>

      <NSelect
        v-if="layoutOptions.length"
        size="tiny"
        :options="layoutOptions"
        placeholder="命名布局"
        :consistent-menu-width="false"
        style="width: 130px"
        @update:value="onApplyLayout"
      />

      <NPopover v-model:show="saveShow" trigger="click" placement="bottom" :width="220">
        <template #trigger>
          <NButton size="tiny">💾 存为</NButton>
        </template>
        <div class="save-pop">
          <NInput v-model:value="saveName" size="small" placeholder="布局名" @keyup.enter="doSave" />
          <NButton size="small" type="primary" block style="margin-top:6px" @click="doSave">保存当前布局</NButton>
          <div class="save-list">
            <NEmpty v-if="!panels.layoutNames.length" size="small" description="尚无命名布局" style="margin-top:8px" />
            <div v-else>
              <div v-for="n in panels.layoutNames" :key="n" class="save-list-row">
                <span class="save-list-name" @click="panels.applyLayout(n); saveShow=false">{{ n }}</span>
                <NButton size="tiny" quaternary class="save-list-del" title="删除" @click="doDelete(n)">✕</NButton>
              </div>
            </div>
          </div>
        </div>
      </NPopover>

      <div style="flex:1"></div>
      <NButton size="tiny" @click="panels.addPanelRight('overview')">＋ 右分屏</NButton>
      <NButton size="tiny" @click="panels.addRow('overview')">＋ 下分行</NButton>
    </div>

    <!-- 主体 -->
    <div class="ws-body">
      <!-- 最大化：只渲染单个面板 -->
      <div v-if="maxPanel" class="ws-max">
        <PanelPane :wid="wid" :panel="maxPanel" />
      </div>
      <!-- 正常：行垂直堆叠，每行内列水平排列 -->
      <Splitpanes v-else class="ws-rows" horizontal>
        <Pane v-for="(row, ri) in panels.rows" :key="ri" class="ws-row-pane">
          <Splitpanes class="ws-cols">
            <Pane v-for="panel in row" :key="panel.id" class="ws-col-pane">
              <PanelPane :wid="wid" :panel="panel" />
            </Pane>
          </Splitpanes>
        </Pane>
      </Splitpanes>
    </div>
  </div>
</template>

<style scoped>
.ws-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.ws-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  flex: 0 0 auto;
  background: var(--n-color, var(--br-sider));
  border-bottom: 1px solid var(--n-border-color, var(--br-border));
}
.ws-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.ws-max {
  height: 100%;
  padding: 6px;
}
/* 让 Splitpanes 撑满 body */
.ws-body :deep(.splitpanes),
.ws-body :deep(.splitpanes__pane) {
  height: 100%;
}
.ws-body :deep(.splitpanes.ws-rows),
.ws-body :deep(.splitpanes.ws-cols) {
  height: 100%;
}
/* 分隔条随主题 */
.ws-body :deep(.splitpanes--vertical > .splitpanes__splitter),
.ws-body :deep(.splitpanes--horizontal > .splitpanes__splitter) {
  background: var(--n-border-color, var(--br-border));
  border-color: var(--n-border-color, var(--br-border));
}
.ws-body :deep(.splitpanes__splitter:hover) {
  background: var(--n-primary-color, var(--br-primary));
}
.ws-col-pane :deep(.splitpanes__pane),
.ws-row-pane {
  overflow: hidden;
}
/* 存为弹层 */
.save-pop { padding: 4px 2px; }
.save-list { margin-top: 8px; border-top: 1px solid var(--br-border-soft); padding-top: 6px; }
.save-list-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
}
.save-list-name {
  color: var(--br-text1);
  cursor: pointer;
  font-size: 13px;
}
.save-list-name:hover { color: var(--br-primary); }
.save-list-del { color: var(--br-text3); }
</style>
