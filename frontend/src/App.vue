<!-- src/App.vue -->
<script setup lang="ts">
import { onMounted, computed, watch, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutHeader, NLayoutContent, NSelect, NMenu, NSpin, NButton, NMessageProvider, NDialogProvider, NConfigProvider, darkTheme } from 'naive-ui'
import { useWorkspace } from './stores/workspace'
import { useThemeStore } from './stores/theme'
import { usePanels } from './stores/panels'
import { isViewKey } from './views/registry'
import ThemePanel from './components/ThemePanel.vue'
import PanelWorkspace from './components/PanelWorkspace.vue'

const ws = useWorkspace()
const theme = useThemeStore()
const panels = usePanels()
const route = useRoute()
const router = useRouter()
const themePanelShow = ref(false)
const siderCollapsed = ref(localStorage.getItem('bedrock-sider') === '1')
function toggleSider() {
  siderCollapsed.value = !siderCollapsed.value
  localStorage.setItem('bedrock-sider', siderCollapsed.value ? '1' : '0')
}
onMounted(() => { ws.loadWorks(); theme.load(); panels.load() })

const workOptions = computed(() => ws.works.map(w => ({ label: `${w.name}（${w.volumes}卷）`, value: w.id })))
watch(() => route.params.wid, (wid) => { if (wid) ws.setActive(wid as string) }, { immediate: true })

function onWork(v: string | null) {
  if (v) { ws.setActive(v); router.push(`/works/${v}`) }
}

const menuOptions = computed(() => {
  const w = ws.activeId
  if (!w) return []
  const base = `/works/${w}`
  return [
    { label: '总览', key: 'overview' },
    { label: '角色', key: 'characters' },
    { label: 'POV 矩阵', key: 'matrix' },
    { label: '灵感池', key: 'inspirations' },
    { label: 'Review 报告', key: 'report' },
    { label: '正文·阅读', key: 'read' },
    { label: '正文·大纲', key: 'outline' },
  ].map(m => ({ label: m.label, key: m.key }))
})

// 侧栏高亮 = 聚焦面板的 view（找不到聚焦面板时回退 overview）
const focusedView = computed(() => {
  for (const row of panels.rows) {
    const p = row.find(x => x.id === panels.focusedId)
    if (p) return p.view
  }
  return 'overview'
})

function onMenu(key: string) {
  if (!ws.activeId || !isViewKey(key)) return
  // 把聚焦面板换成该视图，不再整页跳转
  panels.setFocusedView(key)
}
</script>

<template>
  <NConfigProvider :theme="theme.mode === 'dark' ? darkTheme : null" :theme-overrides="theme.overrides">
  <NMessageProvider>
  <NDialogProvider>
  <NLayout has-sider :style="theme.cssStyleVars" style="height:100vh">
    <NLayoutSider bordered :width="220" :collapsed-width="0" :collapsed="siderCollapsed" :native-scrollbar="true" :content-style="{ padding: '12px', background: 'var(--br-sider)' }">
      <div style="margin-bottom:12px">
        <NSelect v-if="workOptions.length" :value="ws.activeId" :options="workOptions" @update:value="onWork" placeholder="选择作品"/>
        <NSpin v-else size="small"/>
      </div>
      <NMenu :options="menuOptions" :value="focusedView" @update:value="onMenu" :disabled="!ws.activeId" :indent="18" :collapsed-width="220" :collapsed-icon-size="0"/>
      <div style="position:absolute;bottom:8px;font-size:11px;color:var(--br-text3);padding:0 4px">{{ ws.activeId || '未选作品' }}</div>
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered style="height:48px;padding:0 20px;display:flex;align-items:center;background:var(--br-header,var(--br-sider))">
        <NButton quaternary size="small" :title="siderCollapsed ? '展开侧栏' : '折叠侧栏'" style="margin-left:-8px;margin-right:4px" @click="toggleSider">{{ siderCollapsed ? '☰' : '«' }}</NButton>
        <strong :style="{ color: theme.primary }">磐石 Bedrock</strong>
        <span style="margin-left:12px;color:var(--br-text3)">{{ ws.active?.name }}</span>
        <div style="flex:1"></div>
        <NButton quaternary size="small" @click="themePanelShow = true">🎨 主题</NButton>
      </NLayoutHeader>
      <NLayoutContent :content-style="{ padding: '0', background: 'var(--br-page)' }" style="height:calc(100vh - 48px);overflow:hidden">
        <PanelWorkspace v-if="ws.activeId" :wid="ws.activeId" style="height:100%" />
        <div v-else style="color:var(--br-text3);padding:40px">请从左侧选择一个作品。</div>
      </NLayoutContent>
    </NLayout>
  </NLayout>
  <ThemePanel v-model:show="themePanelShow"/>
  </NDialogProvider>
  </NMessageProvider>
  </NConfigProvider>
</template>
