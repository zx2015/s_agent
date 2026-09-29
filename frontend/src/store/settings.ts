/**
 * User settings backing the settings drawer.
 *
 * Defaults mirror the values verified against the local deployment on
 * 2026-09-28, so a fresh install works without configuration.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type HitlMode = 'always' | 'dangerous' | 'never'

export const useSettingsStore = defineStore('settings', () => {
  const modelName = ref('v-flash')
  const baseUrl = ref('http://127.0.0.1:4000/v1')
  const hitlMode = ref<HitlMode>('dangerous')
  const drawerOpen = ref(false)

  function setModel(name: string): void {
    modelName.value = name
  }

  function setBaseUrl(url: string): void {
    baseUrl.value = url
  }

  function setHitlMode(mode: HitlMode): void {
    hitlMode.value = mode
  }

  function openDrawer(): void {
    drawerOpen.value = true
  }

  function closeDrawer(): void {
    drawerOpen.value = false
  }

  return {
    modelName,
    baseUrl,
    hitlMode,
    drawerOpen,
    setModel,
    setBaseUrl,
    setHitlMode,
    openDrawer,
    closeDrawer,
  }
})