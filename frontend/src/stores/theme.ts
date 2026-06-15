// frontend/src/stores/theme.ts
// 响应式主题：primary/radius/mode/font 可调，存 localStorage，App.vue 绑定实时生效。
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { buildOverrides, DEFAULT_PRIMARY, DEFAULT_RADIUS, DEFAULT_MODE, DEFAULT_FONT, type ThemeMode } from '../theme'

const LS_KEY = 'bedrock-theme'

interface Saved { primary: string; radius: number; mode: ThemeMode; font: string }

export const useThemeStore = defineStore('theme', () => {
  const primary = ref(DEFAULT_PRIMARY)
  const radius = ref(DEFAULT_RADIUS)
  const mode = ref<ThemeMode>(DEFAULT_MODE)
  const font = ref(DEFAULT_FONT)
  const overrides = computed(() => buildOverrides({ primary: primary.value, radius: radius.value, mode: mode.value, font: font.value }))
  // Naive NConfigProvider :theme —— dark 用 darkTheme，light 用 null（Naive 默认亮色）
  const naiveTheme = computed(() => mode.value === 'dark' ? 'dark' : null)

  function load() {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return
      const s = JSON.parse(raw) as Partial<Saved>
      if (s.primary && /^#[0-9a-fA-F]{6}$/.test(s.primary)) primary.value = s.primary
      if (typeof s.radius === 'number' && s.radius >= 0 && s.radius <= 20) radius.value = s.radius
      if (s.mode === 'dark' || s.mode === 'light') mode.value = s.mode
      if (typeof s.font === 'string' && s.font) font.value = s.font
    } catch { /* 忽略损坏的存储 */ }
  }

  function snapshot(): Saved {
    return { primary: primary.value, radius: radius.value, mode: mode.value, font: font.value }
  }
  function persist() { try { localStorage.setItem(LS_KEY, JSON.stringify(snapshot())) } catch { /* 忽略 */ } }
  function applySaved(s: Partial<Saved>) {
    if (s.primary && /^#[0-9a-fA-F]{6}$/.test(s.primary)) primary.value = s.primary
    if (typeof s.radius === 'number' && s.radius >= 0 && s.radius <= 20) radius.value = s.radius
    if (s.mode === 'dark' || s.mode === 'light') mode.value = s.mode
    if (typeof s.font === 'string' && s.font) font.value = s.font
    persist()
  }

  function setPrimary(p: string) { primary.value = p; persist() }
  function setRadius(r: number) { radius.value = r; persist() }
  function setMode(m: ThemeMode) { mode.value = m; persist() }
  function setFont(f: string) { font.value = f; persist() }
  function applyPreset(p: string) { primary.value = p; persist() }
  function reset() { primary.value = DEFAULT_PRIMARY; radius.value = DEFAULT_RADIUS; mode.value = DEFAULT_MODE; font.value = DEFAULT_FONT; persist() }

  function exportJSON(): string { return JSON.stringify(snapshot(), null, 2) }
  function importJSON(text: string): boolean {
    try {
      const s = JSON.parse(text) as Partial<Saved>
      if (!s || (!s.primary && !s.radius && !s.mode && !s.font)) return false
      applySaved(s)
      return true
    } catch { return false }
  }

  return { primary, radius, mode, font, overrides, naiveTheme, load, persist, snapshot, applySaved,
    setPrimary, setRadius, setMode, setFont, applyPreset, reset, exportJSON, importJSON }
})
