// src/api/client.ts
const BASE = ''  // 同源（dev 经 vite proxy，prod 同进程）

async function req(method: string, path: string, body?: any) {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 415) throw new Error('请求格式错误（需 JSON）')
  if (res.status === 404) throw new Error('未找到（work_id/资源不存在）')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
  works: () => req('GET', '/api/works'),
  overview: (w: string) => req('GET', `/api/works/${w}/overview`),
  matrix: (w: string, v?: number) => req('GET', `/api/works/${w}/matrix${v ? '?volume=' + v : ''}`),
  matrixBeats: (w: string, chapter: number, character: number) =>
    req('GET', `/api/works/${w}/matrix/beats?chapter=${chapter}&character=${character}`),
  inspirations: (w: string, type?: string, status?: string) =>
    req('GET', `/api/works/${w}/inspirations${[type, status].filter(Boolean).length ? '?' + [type && 'type=' + type, status && 'status=' + status].filter(Boolean).join('&') : ''}`),
  advance: (w: string, id: number, target: string) =>
    req('POST', `/api/works/${w}/inspirations/${id}/advance`, { target }),
  editInspiration: (w: string, id: number, body: any) =>
    req('PATCH', `/api/works/${w}/inspirations/${id}`, body),
  reports: (w: string) => req('GET', `/api/works/${w}/reports`),
  report: (w: string, vid: number) => req('GET', `/api/works/${w}/report/${vid}`),
  chapters: (w: string) => req('GET', `/api/works/${w}/chapters`),
  chapterText: (w: string, g: number) => req('GET', `/api/works/${w}/chapters/${g}/text`),
  outline: (w: string, v?: number) => req('GET', `/api/works/${w}/outline${v ? '?volume=' + v : ''}`),
  characters: (w: string) => req('GET', `/api/works/${w}/characters`),
  factions: (w: string) => req('GET', `/api/works/${w}/factions`),
  style: (w: string) => req('GET', `/api/works/${w}/style`),
  styleActual: (w: string, v?: number) => req('GET', `/api/works/${w}/style/actual${v ? '?volume=' + v : ''}`),
  setStyle: (w: string, body: any) => req('POST', `/api/works/${w}/style`, body),
  patch: (w: string, entity: string, id: number | string, body: any) =>
    req('PATCH', `/api/works/${w}/${entity}/${id}`, body),
  patchBeatContract: (w: string, vid: number, bid: number, body: any) =>
    req('PATCH', `/api/works/${w}/volumes/${vid}/beats/${bid}/contract`, body),
  patchMaster: (w: string, body: any) => req('PATCH', `/api/works/${w}/master_outline`, body),
}
