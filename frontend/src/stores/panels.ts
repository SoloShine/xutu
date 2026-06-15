// src/stores/panels.ts
// 多面板分屏布局 store。布局模型 = rows: Panel[][]（每行若干列）。
// 持久化到 localStorage 'bedrock-panels'，结构损坏时 reset。
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isViewKey, type ViewKey } from '../views/registry'

export interface Panel {
  id: number
  view: ViewKey
}

const LS_KEY = 'bedrock-panels'

type PresetName = 'single' | 'dual' | 'triple' | 'grid'

function makeRows(views: ViewKey[], colsPerRow: number): Panel[][] {
  const rows: Panel[][] = []
  let id = 1
  for (let i = 0; i < views.length; i += colsPerRow) {
    const slice = views.slice(i, i + colsPerRow)
    rows.push(slice.map(v => ({ id: id++, view: v })))
  }
  return rows
}

function preset(name: PresetName): Panel[][] {
  switch (name) {
    case 'single':  return makeRows(['overview'], 1)
    case 'dual':    return makeRows(['overview', 'inspirations'], 2)
    case 'triple':  return makeRows(['overview', 'inspirations', 'outline'], 3)
    case 'grid':    return makeRows(['outline', 'inspirations', 'read', 'characters'], 2)
    default:        return makeRows(['overview'], 1)
  }
}

export const usePanels = defineStore('panels', () => {
  const rows = ref<Panel[][]>(makeRows(['overview'], 1))
  const focusedId = ref<number>(1)
  const idCounter = ref<number>(1)

  function nextId(): number {
    idCounter.value += 1
    return idCounter.value
  }

  function persist() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        rows: rows.value, focusedId: focusedId.value, idCounter: idCounter.value,
      }))
    } catch { /* 忽略存储失败 */ }
  }

  function load() {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) { reset(); return }
      const data = JSON.parse(raw)
      const r = normalizeRows(data?.rows)
      if (!r.length) { reset(); return }
      rows.value = r
      idCounter.value = Number.isFinite(data?.idCounter) ? data.idCounter : Math.max(...allIds(r), 0)
      // 聚焦面板若不存在，回退到第一个面板
      const ids = allIds(r)
      focusedId.value = data?.focusedId && ids.includes(data.focusedId) ? data.focusedId : ids[0]
    } catch {
      reset()
    }
  }

  function reset() {
    rows.value = makeRows(['overview'], 1)
    focusedId.value = 1
    idCounter.value = 1
    persist()
  }

  function focus(id: number) {
    if (allIds(rows.value).includes(id)) {
      focusedId.value = id
      persist()
    }
  }

  // 改某面板视图
  function setPanelView(id: number, view: ViewKey) {
    for (const row of rows.value) {
      const p = row.find(x => x.id === id)
      if (p) { p.view = view; persist(); return }
    }
  }

  // 把聚焦面板视图改成 view（侧栏点击用）；无聚焦面板则默认第一个
  function setFocusedView(view: ViewKey) {
    ensureFocus()
    setPanelView(focusedId.value, view)
  }

  // 在聚焦面板所在行的右侧追加一列，新面板聚焦
  function addPanelRight(view: ViewKey = 'overview') {
    ensureFocus()
    const idx = rowIndexOf(focusedId.value)
    if (idx < 0) { reset(); return }
    const np: Panel = { id: nextId(), view }
    rows.value[idx].push(np)
    focusedId.value = np.id
    persist()
  }

  // 在底部追加一行（1 个面板），新面板聚焦
  function addRow(view: ViewKey = 'overview') {
    const np: Panel = { id: nextId(), view }
    rows.value.push([np])
    focusedId.value = np.id
    persist()
  }

  // 移除面板；行空了删行；全部空了 reset；保证至少 1 个面板
  function closePanel(id: number) {
    for (let i = 0; i < rows.value.length; i++) {
      const j = rows.value[i].findIndex(x => x.id === id)
      if (j >= 0) {
        rows.value[i].splice(j, 1)
        if (rows.value[i].length === 0) rows.value.splice(i, 1)
        break
      }
    }
    if (rows.value.length === 0) { reset(); return }
    const ids = allIds(rows.value)
    if (!ids.includes(focusedId.value)) focusedId.value = ids[0]
    persist()
  }

  function applyPreset(name: PresetName) {
    rows.value = preset(name)
    idCounter.value = Math.max(...allIds(rows.value), 0)
    focusedId.value = allIds(rows.value)[0] ?? 1
    persist()
  }

  // 若当前聚焦面板已不存在，回退到第一个面板
  function ensureFocus() {
    const ids = allIds(rows.value)
    if (!ids.length) { reset(); return }
    if (!ids.includes(focusedId.value)) focusedId.value = ids[0]
  }

  // ---- helpers ----
  function rowIndexOf(panelId: number): number {
    return rows.value.findIndex(r => r.some(p => p.id === panelId))
  }

  function allIds(rs: Panel[][]): number[] {
    const out: number[] = []
    for (const r of rs) for (const p of r) out.push(p.id)
    return out
  }

  // 校验并规范化从 localStorage 读回的 rows：剔除非法结构；返回 [] 表示彻底损坏
  function normalizeRows(raw: unknown): Panel[][] {
    if (!Array.isArray(raw)) return []
    const out: Panel[][] = []
    for (const row of raw) {
      if (!Array.isArray(row)) return []
      const validRow: Panel[] = []
      for (const p of row) {
        if (!p || typeof p !== 'object') return []
        const id = (p as Panel).id
        const view = (p as Panel).view
        if (typeof id !== 'number' || !Number.isFinite(id)) return []
        if (typeof view !== 'string' || !isViewKey(view)) return []
        validRow.push({ id, view })
      }
      out.push(validRow)
    }
    // 至少要有 1 个面板，且无空行
    return out.every(r => r.length > 0) && out.length > 0 ? out : []
  }

  return {
    rows, focusedId,
    load, persist, reset, focus,
    setPanelView, setFocusedView, addPanelRight, addRow, closePanel, applyPreset,
  }
})
