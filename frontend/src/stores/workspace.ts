// src/stores/workspace.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

export interface Work { id: string; name: string; volumes: number; chapters_completed: number; chapters_writing: number }

export const useWorkspace = defineStore('workspace', () => {
  const works = ref<Work[]>([])
  const activeId = ref<string | null>(null)
  const active = computed(() => works.value.find(w => w.id === activeId.value) || null)

  async function loadWorks() { works.value = await api.works() }
  function setActive(id: string) { activeId.value = id }
  async function createWork(name: string, slug?: string) {
    const r = await api.createWork({ name, slug }) as any
    await loadWorks()
    const id = r?.item?.id || r?.id
    if (id) activeId.value = id
    return id
  }

  return { works, activeId, active, loadWorks, setActive, createWork }
})
