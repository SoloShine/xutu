<!-- src/components/PanelWorkspace.vue -->
<!-- 分屏工作站主区：顶部工具栏（布局预设 + 右分屏/下分行）+ 主体（Splitpanes 行×列嵌套）。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NButtonGroup } from 'naive-ui'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import PanelPane from './PanelPane.vue'
import { usePanels } from '../stores/panels'

defineProps<{ wid: string }>()
const panels = usePanels()

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
      <div style="flex:1"></div>
      <NButton size="tiny" @click="panels.addPanelRight('overview')">＋ 右分屏</NButton>
      <NButton size="tiny" @click="panels.addRow('overview')">＋ 下分行</NButton>
    </div>

    <!-- 主体：行垂直堆叠（horizontal），每行内列水平排列 -->
    <div class="ws-body">
      <Splitpanes class="ws-rows" horizontal>
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
  background: var(--n-color, #18181c);
  border-bottom: 1px solid var(--n-border-color, #2a2f3a);
}
.ws-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
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
  background: var(--n-border-color, #2c313c);
  border-color: var(--n-border-color, #2c313c);
}
.ws-body :deep(.splitpanes__splitter:hover) {
  background: var(--n-primary-color, #4ec9b0);
}
.ws-col-pane :deep(.splitpanes__pane),
.ws-row-pane {
  overflow: hidden;
}
</style>
