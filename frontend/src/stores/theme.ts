// frontend/src/stores/theme.ts
// 响应式主题：primary + radius 可调，存 localStorage，App.vue 绑定 overrides 实时生效。
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { buildOverrides, DEFAULT_PRIMARY, DEFAULT_RADIUS } from '../theme'

const LS_KEY = 'bedrock-theme'

interface Saved { primary: string; radius: number }

export const useThemeStore = defineStore('theme', () => {
  const primary = ref(DEFAULT_PRIMARY)
  const radius = ref(DEFAULT_RADIUS)
  const overrides = computed(() => buildOverrides(primary.value, radius.value))

  function load() {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return
      const s = JSON.parse(raw) as Partial<Saved>
      if (s.primary && /^#[0-9a-fA-F]{6}$/.test(s.primary)) primary.value = s.primary
      if (typeof s.radius === 'number' && s.radius >= 0 && s.radius <= 20) radius.value = s.radius
    } catch { /* 忽略损坏的存储 */ }
  }

  function persist() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ primary: primary.value, radius: radius.value } as Saved))
    } catch { /* 忽略 */ }
  }

  function setPrimary(p: string) { primary.value = p; persist() }
  function setRadius(r: number) { radius.value = r; persist() }
  function applyPreset(p: string, r = radius.value) { primary.value = p; radius.value = r; persist() }
  function reset() { primary.value = DEFAULT_PRIMARY; radius.value = DEFAULT_RADIUS; persist() }

  return { primary, radius, overrides, load, setPrimary, setRadius, applyPreset, reset }
})
