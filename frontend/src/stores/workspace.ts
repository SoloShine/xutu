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

  return { works, activeId, active, loadWorks, setActive }
})
