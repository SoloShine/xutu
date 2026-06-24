// src/views/registry.ts
// 视图注册表：所有可放入面板的视图组件统一在此登记。
// 面板布局 store / PanelPane / 侧栏点击都引用此表，避免散落的硬编码 key。
import { defineAsyncComponent } from 'vue'

export const VIEWS = {
  overview:     { label: '总览',        component: defineAsyncComponent(() => import('./Overview.vue')) },
  characters:   { label: '角色',        component: defineAsyncComponent(() => import('./Characters.vue')) },
  matrix:       { label: 'POV 矩阵',    component: defineAsyncComponent(() => import('./Matrix.vue')) },
  style:        { label: '文风指纹',    component: defineAsyncComponent(() => import('./Style.vue')) },
  workflow_config: { label: '工作流配置', component: defineAsyncComponent(() => import('./WorkflowConfig.vue')) },
  endpoints:    { label: 'LLM 端点',    component: defineAsyncComponent(() => import('./Endpoints.vue')) },
  runs:         { label: '运行监控',    component: defineAsyncComponent(() => import('./Runs.vue')) },
  inspirations: { label: '灵感池',      component: defineAsyncComponent(() => import('./Inspirations.vue')) },
  report:       { label: 'Review 报告', component: defineAsyncComponent(() => import('./Report.vue')) },
  read:         { label: '正文·阅读',   component: defineAsyncComponent(() => import('./Reader.vue')) },
  outline:      { label: '正文·大纲',   component: defineAsyncComponent(() => import('./Outline.vue')) },
} as const

export type ViewKey = keyof typeof VIEWS

export const VIEW_KEYS = Object.keys(VIEWS) as ViewKey[]

// NSelect 选项
export const VIEW_OPTIONS = VIEW_KEYS.map(k => ({ label: VIEWS[k].label, value: k }))

export function isViewKey(k: string): k is ViewKey {
  return k in VIEWS
}
