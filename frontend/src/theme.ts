// frontend/src/theme.ts
// 主题构造器 + 颜色助手。主色/圆角/明暗/字体参数化，供主题面板实时调。
import type { GlobalThemeOverrides } from 'naive-ui'

export type ThemeMode = 'dark' | 'light'
export const DEFAULT_PRIMARY = '#4ec9b0'
export const DEFAULT_RADIUS = 6
export const DEFAULT_MODE: ThemeMode = 'dark'
export const DEFAULT_FONT = 'sans'

export interface FontOption { label: string; value: string; stack: string }
export const FONTS: FontOption[] = [
  { label: '无衬线（系统）', value: 'sans', stack: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Roboto, Helvetica, Arial, sans-serif' },
  { label: '衬线（宋体）', value: 'serif', stack: '"Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", Georgia, "Times New Roman", serif' },
  { label: '等宽', value: 'mono', stack: '"JetBrains Mono", "Cascadia Code", "Sarasa Mono SC", Consolas, "Courier New", monospace' },
  { label: '圆体', value: 'round', stack: '"Yuanti SC", "YouSheBiaoTiHei", "Hiragino Maru Gothic Pro", "Microsoft YaHei", sans-serif' },
]

// ---- 颜色助手 ----
export function hexToHsl(hex: string): [number, number, number] {
  let h = hex.replace('#', '')
  if (h.length === 3) h = h.split('').map(c => c + c).join('')
  const r = parseInt(h.slice(0, 2), 16) / 255
  const g = parseInt(h.slice(2, 4), 16) / 255
  const b = parseInt(h.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let hh = 0, s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: hh = (g - b) / d + (g < b ? 6 : 0); break
      case g: hh = (b - r) / d + 2; break
      default: hh = (r - g) / d + 4
    }
    hh /= 6
  }
  return [hh * 360, s * 100, l * 100]
}
export function hslToHex(h: number, s: number, l: number): string {
  s /= 100; l /= 100
  const k = (n: number) => (n + h / 30) % 12
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => {
    const c = l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
    return Math.round(c * 255).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}
export function lighten(hex: string, amt: number): string { const [h, s, l] = hexToHsl(hex); return hslToHex(h, s, Math.min(100, l + amt)) }
export function darken(hex: string, amt: number): string { const [h, s, l] = hexToHsl(hex); return hslToHex(h, s, Math.max(0, l - amt)) }

export interface ThemePreset { label: string; primary: string }
export const PRESETS: ThemePreset[] = [
  { label: '青绿', primary: '#4ec9b0' },
  { label: '湖蓝', primary: '#61afef' },
  { label: '紫', primary: '#c678dd' },
  { label: '琥珀', primary: '#e5c07b' },
  { label: '红', primary: '#e06c6c' },
  { label: '粉', primary: '#ff7ac6' },
]

// 明暗两套中性色
const NEUTRAL = {
  dark: {
    page: '#15171c', card: '#1a1d24', modal: '#1d2128', elevated: '#20242d',
    border: '#2c313c', borderSoft: '#232831',
    text1: '#e6e9ef', text2: '#b8bdc9', text3: '#7c8494', textDisabled: '#5a6270',
    sider: '#18181c', header: '#18181c',
  },
  light: {
    page: '#f4f5f7', card: '#ffffff', modal: '#ffffff', elevated: '#eef0f4',
    border: '#e2e5ea', borderSoft: '#edeff2',
    text1: '#1f2329', text2: '#4e5969', text3: '#86909c', textDisabled: '#c9cdd4',
    sider: '#ffffff', header: '#ffffff',
  },
}

export interface ThemeParams { primary: string; radius: number; mode: ThemeMode; font: string }

export function buildOverrides(p: ThemeParams): GlobalThemeOverrides {
  const n = NEUTRAL[p.mode]
  // 深色：hover 提亮、pressed 加深；浅色：hover 加深、pressed 更深
  const hover = p.mode === 'dark' ? lighten(p.primary, 12) : darken(p.primary, 6)
  const pressed = darken(p.primary, p.mode === 'dark' ? 14 : 14)
  const fontStack = (FONTS.find(f => f.value === p.font) || FONTS[0]).stack
  const r = `${p.radius}px`
  const rSm = `${Math.max(2, p.radius - 2)}px`
  return {
    common: {
      primaryColor: p.primary, primaryColorHover: hover, primaryColorPressed: pressed, primaryColorSuppl: hover,
      bodyColor: n.page, cardColor: n.card, modalColor: n.modal, popoverColor: n.elevated,
      tableColor: n.card, tableHeaderColor: n.elevated, inputColor: n.elevated, inputColorDisabled: n.card,
      actionColor: n.elevated, hoverColor: `${p.primary}14`, borderColor: n.border, dividerColor: n.borderSoft,
      textColor1: n.text1, textColor2: n.text2, textColor3: n.text3, textColorDisabled: n.textDisabled,
      placeholderColor: n.text3, iconColor: n.text2, iconColorHover: p.primary,
      borderRadius: r, borderRadiusSmall: rSm, fontFamily: fontStack, fontSize: '14px', fontSizeSmall: '13px',
    },
    Card: { color: n.card, colorModal: n.modal, borderColor: n.border, borderRadius: `${p.radius + 4}px`, paddingMedium: '16px 20px', titleFontSizeMedium: '15px', titleFontWeight: '600' },
    Button: { borderRadiusMedium: r, borderRadiusSmall: rSm, fontWeight: '500' },
    Tag: { borderRadius: '999px', fontWeightStrong: '600' },
    DataTable: {
      thColor: n.elevated, thColorHover: n.elevated, tdColor: n.card, tdColorHover: `${p.primary}0d`,
      borderColor: n.borderSoft, thTextColor: n.text2, tdTextColor: n.text1, thFontWeight: '600',
      borderRadius: `${p.radius + 4}px`, fontSizeMedium: '13.5px',
    },
    Menu: {
      itemHeight: '38px', borderRadius: r,
      itemColorActive: `${p.primary}1f`, itemColorActiveHover: `${p.primary}29`, itemColorHover: n.elevated,
      itemTextColorActive: p.primary, itemTextColorActiveHover: p.primary, itemTextColorHoverHorizontal: n.text1, arrowColorActive: p.primary,
    },
    Input: { borderHover: `1px solid ${pressed}`, borderFocus: `1px solid ${p.primary}`, boxShadowFocus: `0 0 0 2px ${p.primary}26`, borderRadius: r },
    Select: { peers: { InternalSelection: { borderRadius: r } } },
    Layout: { color: n.page, siderColor: n.sider, headerColor: n.header },
    Statistic: { valueFontWeight: '600', valueTextColor: n.text1, labelTextColor: n.text3 },
    Alert: { borderRadius: `${p.radius + 2}px` },
    Modal: { borderRadius: `${p.radius + 6}px` },
    Drawer: { borderRadius: '0px' },
    Empty: { textColor: n.text3 },
  }
}

// 语义 CSS 变量：暴露 NEUTRAL 色板 + 主色为 CSS custom properties，
// 供各视图 scoped style 用 var(--br-xxx) 引用，从而随 mode 切换实时生效。
// （Naive 组件走 themeOverrides；scoped style 里的字面 hex 不受 themeOverrides 影响，必须用 CSS 变量。）
export const CSS_VARS = [
  'page', 'sider', 'card', 'elevated', 'modal', 'border', 'border-soft',
  'text1', 'text2', 'text3', 'text-disabled', 'primary',
] as const
export type CssVarName = (typeof CSS_VARS)[number]

export function cssVars(p: ThemeParams): Record<string, string> {
  const n = NEUTRAL[p.mode]
  return {
    '--br-page': n.page,
    '--br-sider': n.sider,
    '--br-card': n.card,
    '--br-elevated': n.elevated,
    '--br-modal': n.modal,
    '--br-border': n.border,
    '--br-border-soft': n.borderSoft,
    '--br-text1': n.text1,
    '--br-text2': n.text2,
    '--br-text3': n.text3,
    '--br-text-disabled': n.textDisabled,
    '--br-primary': p.primary,
  }
}

export const themeOverrides: GlobalThemeOverrides = buildOverrides({ primary: DEFAULT_PRIMARY, radius: DEFAULT_RADIUS, mode: DEFAULT_MODE, font: DEFAULT_FONT })
