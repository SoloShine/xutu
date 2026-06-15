<!-- src/components/PanelPane.vue -->
<!-- 单面板：头部条（视图切换 NSelect + 关闭）+ body（渲染对应视图组件）。
     点击聚焦；聚焦时头部加主色边框。各视图实例用 panel.id 作 key 保证独立。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { NSelect, NButton } from 'naive-ui'
import { VIEWS, VIEW_OPTIONS, type ViewKey } from '../views/registry'
import { usePanels } from '../stores/panels'

const props = defineProps<{ wid: string; panel: { id: number; view: ViewKey } }>()
const panels = usePanels()

const viewComp = computed(() => VIEWS[props.panel.view].component)
const focused = computed(() => panels.focusedId === props.panel.id)

function onViewChange(v: ViewKey) { panels.setPanelView(props.panel.id, v) }
function onClose() { panels.closePanel(props.panel.id) }
function onFocus() { panels.focus(props.panel.id) }
</script>

<template>
  <div class="panel-pane" :class="{ focused }" @click="onFocus">
    <div class="panel-head" @click.stop="onFocus">
      <NSelect
        size="tiny"
        :value="panel.view"
        :options="VIEW_OPTIONS"
        :consistent-menu-width="false"
        style="width: 130px"
        @update:value="onViewChange"
      />
      <div style="flex:1"></div>
      <NButton size="tiny" quaternary class="panel-close" title="关闭面板" @click.stop="onClose">✕</NButton>
    </div>
    <div class="panel-body">
      <component :is="viewComp" :wid="wid" :key="panel.id" />
    </div>
  </div>
</template>

<style scoped>
.panel-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--n-border-color, var(--br-border));
  border-radius: 4px;
  overflow: hidden;
  background: var(--body-bg, var(--br-page));
}
.panel-pane.focused {
  border-color: var(--n-primary-color, var(--br-primary));
  box-shadow: 0 0 0 1px var(--n-primary-color, var(--br-primary)) inset;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: var(--n-color, var(--br-card));
  border-bottom: 1px solid var(--n-border-color, var(--br-border));
  flex: 0 0 auto;
}
.panel-pane.focused .panel-head {
  background: color-mix(in srgb, var(--n-primary-color, var(--br-primary)) 12%, var(--n-color, var(--br-card)));
}
.panel-close {
  color: var(--br-text3);
}
.panel-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
</style>
