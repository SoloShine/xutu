<!-- frontend/src/components/ThemePanel.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { NDrawer, NDrawerContent, NColorPicker, NSlider, NButton, NSpace, NDivider, NText, NSelect, NRadioGroup, NRadio, NInput, useMessage } from 'naive-ui'
import { useThemeStore } from '../stores/theme'
import { PRESETS, FONTS } from '../theme'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()
const theme = useThemeStore()
const msg = useMessage()

const colorSwatches = ['#4ec9b0', '#61afef', '#c678dd', '#e5c07b', '#e06c6c', '#ff7ac6', '#98c379', '#56b6c2', '#d19a66', '#abb2bf']
const fontOptions = FONTS.map(f => ({ label: f.label, value: f.value }))

const importShow = ref(false)
const importText = ref('')

function onPreset(primary: string) { theme.applyPreset(primary) }
function onReset() { theme.reset(); msg.success('已恢复默认') }
function onExport() {
  const json = theme.exportJSON()
  navigator.clipboard?.writeText(json).then(
    () => msg.success('主题 JSON 已复制到剪贴板'),
    () => { importText.value = json; importShow.value = true; msg.info('剪贴板不可用，已转导入框') },
  )
}
function onImportApply() {
  if (theme.importJSON(importText.value)) { msg.success('已导入'); importShow.value = false }
  else msg.error('JSON 无效')
}
</script>

<template>
  <NDrawer :show="props.show" :width="360" placement="right" @update:show="emit('update:show', $event)">
    <NDrawerContent title="主题自定义" closable>
      <NSpace vertical :size="18">

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">外观模式</NText>
          <NRadioGroup :value="theme.mode" @update:value="theme.setMode($event)" style="margin-top:10px;display:flex;gap:16px">
            <NRadio value="dark">深色</NRadio>
            <NRadio value="light">浅色</NRadio>
          </NRadioGroup>
        </div>

        <NDivider style="margin:0" />

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">预设主色</NText>
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">
            <button v-for="p in PRESETS" :key="p.primary" @click="onPreset(p.primary)" :title="p.label"
              :style="{ width:'34px', height:'34px', borderRadius:'8px', cursor:'pointer', background:p.primary,
                border: theme.primary.toLowerCase()===p.primary.toLowerCase() ? '2px solid #fff' : '2px solid transparent',
                boxShadow: theme.primary.toLowerCase()===p.primary.toLowerCase() ? `0 0 0 2px ${p.primary}` : 'none' }" />
          </div>
          <div style="margin-top:12px">
            <NColorPicker :value="theme.primary" :show-alpha="false" :swatches="colorSwatches" @update:value="theme.setPrimary($event)" />
          </div>
        </div>

        <NDivider style="margin:0" />

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">圆角 {{ theme.radius }}px</NText>
          <NSlider :value="theme.radius" :min="0" :max="16" :step="1" :marks="{ 0:'直角', 6:'默认', 12:'大', 16:'圆' }" style="margin-top:12px" @update:value="theme.setRadius($event)" />
        </div>

        <NDivider style="margin:0" />

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">字体</NText>
          <NSelect :value="theme.font" :options="fontOptions" style="margin-top:10px" @update:value="theme.setFont($event)" />
        </div>

        <NDivider style="margin:0" />

        <div style="background:var(--n-color,var(--br-card));border:1px solid var(--n-border-color,var(--br-border));border-radius:10px;padding:14px">
          <NText depth="3" style="font-size:12px">实时预览</NText>
          <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
            <NButton type="primary" size="small">主按钮</NButton>
            <NButton size="small">默认</NButton>
            <NButton type="primary" tertiary size="small">tertiary</NButton>
          </div>
        </div>

        <NSpace justify="space-between">
          <NButton size="small" @click="onExport">导出 JSON</NButton>
          <NButton size="small" quaternary @click="importShow = true; importText = ''">导入</NButton>
          <NButton size="small" @click="onReset">恢复默认</NButton>
        </NSpace>

      </NSpace>
    </NDrawerContent>
  </NDrawer>

  <NDrawer :show="importShow" :width="420" placement="right" @update:show="importShow = $event">
    <NDrawerContent title="导入主题 JSON" closable>
      <NInput v-model:value="importText" type="textarea" :rows="12" placeholder='{"primary":"#4ec9b0","radius":6,"mode":"dark","font":"sans"}' style="font-family:monospace;font-size:12px" />
      <template #footer>
        <NSpace justify="end">
          <NButton size="small" @click="importShow = false">取消</NButton>
          <NButton size="small" type="primary" @click="onImportApply">应用</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
