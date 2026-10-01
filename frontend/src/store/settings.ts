/**
 * User settings backing the settings drawer.
 *
 * Defaults mirror the values verified against the local deployment on
 * 2026-09-28, so a fresh install works without configuration.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient } from '../api/client'

export type HitlMode = 'always' | 'dangerous' | 'never'
export type AppTheme = 'light' | 'dark'

export const useSettingsStore = defineStore('settings', () => {
  const modelName = ref('v-flash')
  const baseUrl = ref('http://127.0.0.1:4000/v1')
  const hitlMode = ref<HitlMode>('dangerous')
  const drawerOpen = ref(false)
  const workspaceRoot = ref('')
  const availableModels = ref<string[]>([
    'v-flash',
    'claude-3-5-sonnet',
    'gpt-4o',
    'deepseek-chat',
    'qwen-plus',
  ])

  const initialTheme = (typeof localStorage !== 'undefined' && (localStorage.getItem('s_agent_theme') as AppTheme)) || 'light'
  const theme = ref<AppTheme>(initialTheme)
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', initialTheme)
  }

  function setModel(name: string): void {
    modelName.value = name
  }

  function setBaseUrl(url: string): void {
    baseUrl.value = url
  }

  function setHitlMode(mode: HitlMode): void {
    hitlMode.value = mode
  }

  function setTheme(newTheme: AppTheme): void {
    theme.value = newTheme
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('s_agent_theme', newTheme)
    }
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', newTheme)
    }
  }

  function openDrawer(): void {
    drawerOpen.value = true
  }

  function closeDrawer(): void {
    drawerOpen.value = false
  }

  async function fetchSystemInfo(): Promise<void> {
    try {
      const info = await apiClient.get<{
        workspaceRoot: string
        modelName?: string
        baseUrl?: string
        hitlMode?: HitlMode
      }>('/api/system/info')
      if (info.workspaceRoot) {
        workspaceRoot.value = info.workspaceRoot
      }
    } catch (err) {
      console.warn('Failed to fetch system info:', err)
    }
  }

  return {
    modelName,
    baseUrl,
    hitlMode,
    drawerOpen,
    workspaceRoot,
    availableModels,
    theme,
    setModel,
    setBaseUrl,
    setHitlMode,
    setTheme,
    openDrawer,
    closeDrawer,
    fetchSystemInfo,
  }
})