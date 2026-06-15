<!-- frontend/src/components/ThemePanel.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { NDrawer, NDrawerContent, NColorPicker, NSlider, NButton, NSpace, NDivider, NText } from 'naive-ui'
import { useThemeStore } from '../stores/theme'
import { PRESETS, DEFAULT_RADIUS, DEFAULT_PRIMARY } from '../theme'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()

const theme = useThemeStore()

const colorSwatches = [
  '#4ec9b0', '#61afef', '#c678dd', '#e5c07b', '#e06c6c', '#ff7ac6',
  '#98c379', '#56b6c2', '#d19a66', '#abb2bf',
]

function onPreset(primary: string) { theme.applyPreset(primary) }
function onReset() { theme.reset() }
</script>

<template>
  <NDrawer :show="props.show" :width="340" placement="right" @update:show="emit('update:show', $event)">
    <NDrawerContent title="主题自定义" closable>
      <NSpace vertical :size="20">
        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">预设主色</NText>
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">
            <button
              v-for="p in PRESETS" :key="p.primary"
              @click="onPreset(p.primary)"
              :title="p.label"
              :style="{
                width:'34px', height:'34px', borderRadius:'8px', cursor:'pointer',
                background:p.primary, border: theme.primary.toLowerCase()===p.primary.toLowerCase() ? '2px solid #fff' : '2px solid transparent',
                boxShadow: theme.primary.toLowerCase()===p.primary.toLowerCase() ? `0 0 0 2px ${p.primary}` : 'none'
              }"
            />
          </div>
        </div>

        <NDivider style="margin:0" />

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">自定义主色</NText>
          <div style="margin-top:10px">
            <NColorPicker
              :value="theme.primary"
              :show-alpha="false"
              :swatches="colorSwatches"
              @update:value="theme.setPrimary($event)"
            />
          </div>
        </div>

        <NDivider style="margin:0" />

        <div>
          <NText depth="2" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px">圆角 {{ theme.radius }}px</NText>
          <NSlider
            :value="theme.radius"
            :min="0" :max="16" :step="1" :marks="{ 0:'直角', 6:'默认', 12:'大', 16:'圆' }"
            style="margin-top:12px"
            @update:value="theme.setRadius($event)"
          />
        </div>

        <NDivider style="margin:0" />

        <div style="background:#1a1d24;border:1px solid #2c313c;border-radius:10px;padding:14px">
          <NText depth="3" style="font-size:12px">实时预览</NText>
          <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
            <NButton type="primary" size="small">主按钮</NButton>
            <NButton size="small">默认</NButton>
            <NButton type="primary" tertiary size="small">tertiary</NButton>
          </div>
        </div>

        <NSpace justify="end">
          <NButton size="small" @click="onReset">恢复默认</NButton>
        </NSpace>
      </NSpace>
    </NDrawerContent>
  </NDrawer>
</template>
