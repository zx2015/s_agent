import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '@/store/settings'

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('defaults to the locally verified model', () => {
    const store = useSettingsStore()
    expect(store.modelName).toBe('v-flash')
    expect(store.baseUrl).toBe('http://127.0.0.1:4000/v1')
  })

  it('defaults to confirming only high-risk actions', () => {
    const store = useSettingsStore()
    expect(store.hitlMode).toBe('dangerous')
  })

  it('updates the model', () => {
    const store = useSettingsStore()
    store.setModel('other-model')
    expect(store.modelName).toBe('other-model')
  })

  it('cycles through HITL modes', () => {
    const store = useSettingsStore()
    store.setHitlMode('always')
    expect(store.hitlMode).toBe('always')
    store.setHitlMode('never')
    expect(store.hitlMode).toBe('never')
  })

  it('opens and closes the drawer', () => {
    const store = useSettingsStore()
    expect(store.drawerOpen).toBe(false)
    store.openDrawer()
    expect(store.drawerOpen).toBe(true)
    store.closeDrawer()
    expect(store.drawerOpen).toBe(false)
  })
})