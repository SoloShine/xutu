<!-- src/components/PanelPane.vue -->
<!-- 单面板：头部条（拖拽手柄 + 视图切换 NSelect + 最大化 + 关闭）+ body（渲染对应视图组件）。
     点击聚焦；聚焦时头部加主色边框。各视图实例用 panel.id 作 key 保证独立。
     头部可拖拽到另一面板实现换位；⤢ 切换最大化。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { NSelect, NButton } from 'naive-ui'
import { VIEWS, VIEW_OPTIONS, type ViewKey } from '../views/registry'
import { usePanels } from '../stores/panels'

const props = defineProps<{ wid: string; panel: { id: number; view: ViewKey } }>()
const panels = usePanels()

const viewComp = computed(() => VIEWS[props.panel.view].component)
const focused = computed(() => panels.focusedId === props.panel.id)
const maximized = computed(() => panels.maximizedId === props.panel.id)
const dragOver = ref(false)

function onViewChange(v: ViewKey) { panels.setPanelView(props.panel.id, v) }
function onClose() { panels.closePanel(props.panel.id) }
function onFocus() { panels.focus(props.panel.id) }
function onToggleMax() { panels.toggleMaximize(props.panel.id) }

// ---- 拖拽换位 ----
function onDragStart(e: DragEvent) {
  panels.dragId = props.panel.id
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    // Firefox 需要 setData 才会真正触发 drag
    e.dataTransfer.setData('text/plain', String(props.panel.id))
  }
}
function onDragEnd() {
  panels.dragId = null
  dragOver.value = false
}
function onDragOver(e: DragEvent) {
  if (panels.dragId !== null && panels.dragId !== props.panel.id) {
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    dragOver.value = true
  }
}
function onDragLeave() { dragOver.value = false }
function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  if (panels.dragId !== null && panels.dragId !== props.panel.id) {
    panels.swapPanels(panels.dragId, props.panel.id)
  }
  panels.dragId = null
}
</script>

<template>
  <div class="panel-pane" :class="{ focused, maximized, 'drag-over': dragOver }" @click="onFocus">
    <div
      class="panel-head"
      draggable="true"
      @click.stop="onFocus"
      @dragstart="onDragStart"
      @dragend="onDragEnd"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <span class="drag-handle" title="拖到其他面板换位">⠿</span>
      <NSelect
        size="tiny"
        :value="panel.view"
        :options="VIEW_OPTIONS"
        :consistent-menu-width="false"
        style="width: 130px"
        @update:value="onViewChange"
      />
      <div style="flex:1"></div>
      <NButton size="tiny" quaternary class="panel-icon-btn" :title="maximized ? '还原' : '最大化'" @click.stop="onToggleMax">{{ maximized ? '⤡' : '⤢' }}</NButton>
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
.panel-pane.drag-over {
  outline: 2px dashed var(--n-primary-color, var(--br-primary));
  outline-offset: -3px;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: var(--n-color, var(--br-card));
  border-bottom: 1px solid var(--n-border-color, var(--br-border));
  flex: 0 0 auto;
  cursor: grab;
}
.panel-head:active { cursor: grabbing; }
.panel-pane.focused .panel-head {
  background: color-mix(in srgb, var(--n-primary-color, var(--br-primary)) 12%, var(--n-color, var(--br-card)));
}
.drag-handle {
  color: var(--br-text3);
  font-size: 14px;
  line-height: 1;
  cursor: grab;
  user-select: none;
  flex: 0 0 auto;
}
.panel-close,
.panel-icon-btn {
  color: var(--br-text3);
}
.panel-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
</style>
