// frontend/src/theme.ts
// 精炼深色主题 overrides —— 让 Naive 所有组件统一到 青色(#4ec9b0)+深灰中性 体系。
// 喂给 NConfigProvider :theme-overrides。common 的色变量驱动绝大多数组件。
import type { GlobalThemeOverrides } from 'naive-ui'

// 青色主色派生（naive 不从 hex 自动派生 hover/pressed/suppl，需显式给）
const TEAL = '#4ec9b0'
const TEAL_HOVER = '#6fd6c2'
const TEAL_PRESSED = '#3aa890'

// 中性深灰尺度（与各视图既有用色一致）
const BG_PAGE = '#15171c' // 页面底层
const BG_CARD = '#1a1d24' // 卡片/面板
const BG_ELEVATED = '#20242d' // 表头/悬浮/输入
const BG_INPUT = '#20242d'
const BORDER = '#2c313c'
const BORDER_SOFT = '#232831'

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: TEAL,
    primaryColorHover: TEAL_HOVER,
    primaryColorPressed: TEAL_PRESSED,
    primaryColorSuppl: TEAL_HOVER,

    bodyColor: BG_PAGE,
    cardColor: BG_CARD,
    modalColor: '#1d2128',
    popoverColor: BG_ELEVATED,
    tableColor: BG_CARD,
    tableHeaderColor: BG_ELEVATED,
    inputColor: BG_INPUT,
    inputColorDisabled: BG_CARD,
    actionColor: BG_ELEVATED,
    hoverColor: 'rgba(78,201,176,0.08)',
    borderColor: BORDER,
    dividerColor: BORDER_SOFT,

    textColor1: '#e6e9ef',
    textColor2: '#b8bdc9',
    textColor3: '#7c8494',
    textColorDisabled: '#5a6270',
    placeholderColor: '#7c8494',
    iconColor: '#b8bdc9',
    iconColorHover: TEAL,

    borderRadius: '6px',
    borderRadiusSmall: '4px',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Roboto, Helvetica, Arial, sans-serif',
    fontSize: '14px',
    fontSizeSmall: '13px',
  },
  Card: {
    color: BG_CARD,
    colorModal: '#1d2128',
    borderColor: BORDER,
    borderRadius: '10px',
    paddingMedium: '16px 20px',
    titleFontSizeMedium: '15px',
    titleFontWeight: '600',
  },
  Button: {
    borderRadiusMedium: '6px',
    borderRadiusSmall: '4px',
    fontWeight: '500',
  },
  Tag: {
    borderRadius: '999px',
    fontWeightStrong: '600',
  },
  DataTable: {
    thColor: BG_ELEVATED,
    thColorHover: BG_ELEVATED,
    tdColor: BG_CARD,
    tdColorHover: 'rgba(78,201,176,0.05)',
    borderColor: BORDER_SOFT,
    thTextColor: '#b8bdc9',
    tdTextColor: '#e6e9ef',
    thFontWeight: '600',
    borderRadius: '10px',
    fontSizeMedium: '13.5px',
  },
  Menu: {
    itemHeight: '38px',
    borderRadius: '6px',
    itemColorActive: 'rgba(78,201,176,0.12)',
    itemColorActiveHover: 'rgba(78,201,176,0.16)',
    itemColorHover: BG_ELEVATED,
    itemTextColorActive: TEAL,
    itemTextColorActiveHover: TEAL,
    itemTextColorHoverHorizontal: '#e6e9ef',
    arrowColorActive: TEAL,
  },
  Input: {
    borderHover: `1px solid ${TEAL_PRESSED}`,
    borderFocus: `1px solid ${TEAL}`,
    boxShadowFocus: `0 0 0 2px rgba(78,201,176,0.15)`,
    borderRadius: '6px',
  },
  Select: { peers: { InternalSelection: { borderRadius: '6px' } } },
  Layout: {
    color: BG_PAGE,
    siderColor: '#18181c',
    headerColor: '#18181c',
  },
  Statistic: {
    valueFontWeight: '600',
    valueTextColor: '#e6e9ef',
    labelTextColor: '#7c8494',
  },
  Alert: { borderRadius: '8px' },
  Modal: { borderRadius: '12px' },
  Drawer: { borderRadius: '0px' },
  Empty: { textColor: '#7c8494' },
}
