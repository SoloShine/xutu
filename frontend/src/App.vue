<!-- src/App.vue -->
<script setup lang="ts">
import { onMounted, computed, watch, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutHeader, NLayoutContent, NSelect, NMenu, NSpin, NButton, NMessageProvider, NDialogProvider, NConfigProvider, darkTheme } from 'naive-ui'
import { useWorkspace } from './stores/workspace'
import { useThemeStore } from './stores/theme'
import ThemePanel from './components/ThemePanel.vue'

const ws = useWorkspace()
const theme = useThemeStore()
const route = useRoute()
const router = useRouter()
const themePanelShow = ref(false)
onMounted(() => { ws.loadWorks(); theme.load() })

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

// 当前激活的菜单 key（从路由末段反推，用于高亮）
const activeMenuKey = computed(() => {
  const seg = route.path.split('/').filter(Boolean).pop() || 'overview'
  const known = ['overview', 'characters', 'matrix', 'inspirations', 'report', 'read', 'outline']
  return known.includes(seg) ? seg : 'overview'
})

function onMenu(key: string) {
  const w = ws.activeId
  if (!w) return
  router.push(key === 'overview' ? `/works/${w}` : `/works/${w}/${key}`)
}
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="theme.overrides">
  <NMessageProvider>
  <NDialogProvider>
  <NLayout has-sider style="height:100vh">
    <NLayoutSider bordered :width="220" content-style="padding:12px;background:#18181c">
      <div style="margin-bottom:12px">
        <NSelect v-if="workOptions.length" :value="ws.activeId" :options="workOptions" @update:value="onWork" placeholder="选择作品"/>
        <NSpin v-else size="small"/>
      </div>
      <NMenu :options="menuOptions" :value="activeMenuKey" @update:value="onMenu" :disabled="!ws.activeId" :indent="18" :collapsed-width="220" :collapsed-icon-size="0"/>
      <div style="position:absolute;bottom:8px;font-size:11px;color:#666;padding:0 4px">{{ ws.activeId || '未选作品' }}</div>
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered style="height:48px;padding:0 20px;display:flex;align-items:center;background:#18181c">
        <strong :style="{ color: theme.primary }">磐石 Bedrock</strong>
        <span style="margin-left:12px;color:#888">{{ ws.active?.name }}</span>
        <div style="flex:1"></div>
        <NButton quaternary size="small" @click="themePanelShow = true">🎨 主题</NButton>
      </NLayoutHeader>
      <NLayoutContent content-style="padding:20px;background:#15171c" style="height:calc(100vh - 48px);overflow:auto">
        <RouterView v-if="ws.activeId" />
        <div v-else style="color:#666;padding:40px">请从左侧选择一个作品。</div>
      </NLayoutContent>
    </NLayout>
  </NLayout>
  <ThemePanel v-model:show="themePanelShow"/>
  </NDialogProvider>
  </NMessageProvider>
  </NConfigProvider>
</template>
