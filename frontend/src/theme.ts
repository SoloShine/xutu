// frontend/src/theme.ts
// 深色主题构造器 + 颜色助手。主色/圆角参数化，供主题自定义面板实时调。
// 静态中性色固定；主色派生 hover/pressed/suppl（naive 不从 hex 自动派生）。
import type { GlobalThemeOverrides } from 'naive-ui'

export const DEFAULT_PRIMARY = '#4ec9b0'
export const DEFAULT_RADIUS = 6

// 中性深灰尺度（固定，不随主色变）
const BG_PAGE = '#15171c'
const BG_CARD = '#1a1d24'
const BG_ELEVATED = '#20242d'
const BORDER = '#2c313c'
const BORDER_SOFT = '#232831'

// ---- 颜色助手：hex<->hsl + 明暗派生 ----
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

export function lighten(hex: string, amt: number): string {
  const [h, s, l] = hexToHsl(hex)
  return hslToHex(h, s, Math.min(100, l + amt))
}
export function darken(hex: string, amt: number): string {
  const [h, s, l] = hexToHsl(hex)
  return hslToHex(h, s, Math.max(0, l - amt))
}

// ---- 预设主色 ----
export interface ThemePreset { label: string; primary: string }
export const PRESETS: ThemePreset[] = [
  { label: '青绿', primary: '#4ec9b0' },
  { label: '湖蓝', primary: '#61afef' },
  { label: '紫', primary: '#c678dd' },
  { label: '琥珀', primary: '#e5c07b' },
  { label: '红', primary: '#e06c6c' },
  { label: '粉', primary: '#ff7ac6' },
]

// ---- 构造完整 overrides ----
export function buildOverrides(primary: string, radius: number): GlobalThemeOverrides {
  const hover = lighten(primary, 12)
  const pressed = darken(primary, 14)
  const r = `${radius}px`
  return {
    common: {
      primaryColor: primary,
      primaryColorHover: hover,
      primaryColorPressed: pressed,
      primaryColorSuppl: hover,
      bodyColor: BG_PAGE,
      cardColor: BG_CARD,
      modalColor: '#1d2128',
      popoverColor: BG_ELEVATED,
      tableColor: BG_CARD,
      tableHeaderColor: BG_ELEVATED,
      inputColor: BG_ELEVATED,
      inputColorDisabled: BG_CARD,
      actionColor: BG_ELEVATED,
      hoverColor: `${primary}14`, // 8% 透明主色作 hover
      borderColor: BORDER,
      dividerColor: BORDER_SOFT,
      textColor1: '#e6e9ef',
      textColor2: '#b8bdc9',
      textColor3: '#7c8494',
      textColorDisabled: '#5a6270',
      placeholderColor: '#7c8494',
      iconColor: '#b8bdc9',
      iconColorHover: primary,
      borderRadius: r,
      borderRadiusSmall: `${Math.max(2, radius - 2)}px`,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Roboto, Helvetica, Arial, sans-serif',
      fontSize: '14px',
      fontSizeSmall: '13px',
    },
    Card: { color: BG_CARD, colorModal: '#1d2128', borderColor: BORDER, borderRadius: `${radius + 4}px`, paddingMedium: '16px 20px', titleFontSizeMedium: '15px', titleFontWeight: '600' },
    Button: { borderRadiusMedium: r, borderRadiusSmall: `${Math.max(2, radius - 2)}px`, fontWeight: '500' },
    Tag: { borderRadius: '999px', fontWeightStrong: '600' },
    DataTable: {
      thColor: BG_ELEVATED, thColorHover: BG_ELEVATED, tdColor: BG_CARD,
      tdColorHover: `${primary}0d`, borderColor: BORDER_SOFT, thTextColor: '#b8bdc9',
      tdTextColor: '#e6e9ef', thFontWeight: '600', borderRadius: `${radius + 4}px`, fontSizeMedium: '13.5px',
    },
    Menu: {
      itemHeight: '38px', borderRadius: r,
      itemColorActive: `${primary}1f`, itemColorActiveHover: `${primary}29`,
      itemColorHover: BG_ELEVATED, itemTextColorActive: primary, itemTextColorActiveHover: primary,
      itemTextColorHoverHorizontal: '#e6e9ef', arrowColorActive: primary,
    },
    Input: {
      borderHover: `1px solid ${pressed}`, borderFocus: `1px solid ${primary}`,
      boxShadowFocus: `0 0 0 2px ${primary}26`, borderRadius: r,
    },
    Select: { peers: { InternalSelection: { borderRadius: r } } },
    Layout: { color: BG_PAGE, siderColor: '#18181c', headerColor: '#18181c' },
    Statistic: { valueFontWeight: '600', valueTextColor: '#e6e9ef', labelTextColor: '#7c8494' },
    Alert: { borderRadius: `${radius + 2}px` },
    Modal: { borderRadius: `${radius + 6}px` },
    Drawer: { borderRadius: '0px' },
    Empty: { textColor: '#7c8494' },
  }
}

// 默认主题（无自定义时）
export const themeOverrides: GlobalThemeOverrides = buildOverrides(DEFAULT_PRIMARY, DEFAULT_RADIUS)
