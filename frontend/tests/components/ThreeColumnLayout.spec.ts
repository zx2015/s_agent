import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from '@/App.vue'
import { useSessionStore } from '@/store/session'
import type { ParsedFrame } from '@/api/events'

/**
 * Mounting the whole shell is the integration check for Task 12: it proves
 * the three panes, the drawer and the stores wire together without a
 * missing import or a prop mismatch — something per-component tests
 * cannot catch.
 */
describe('App shell (three-column workbench)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
  })

  it('renders the top bar and the three panes', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('s_agent 工作台')
    expect(wrapper.find('.sidebar-left').exists()).toBe(true)
    expect(wrapper.find('.sidebar-middle').exists()).toBe(true)
  })

  it('keeps the right pane collapsed until an artifact arrives', () => {
    const wrapper = mount(App)
    expect(wrapper.find('.sidebar-right').exists()).toBe(false)
  })

  it('expands the right pane when an artifact is announced', async () => {
    const session = useSessionStore()
    const wrapper = mount(App)

    session.applyFrame({
      event: 'artifact_created',
      data: { type: 'html', file_path: 'index.html', url: '/api/x' },
    } as ParsedFrame)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.sidebar-right').exists()).toBe(true)
  })

  it('renders the settings drawer when opened', async () => {
    const wrapper = mount(App)
    expect(wrapper.find('.drawer').exists()).toBe(false)

    const { useSettingsStore } = await import('@/store/settings')
    useSettingsStore().openDrawer()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.drawer').exists()).toBe(true)
  })

  it('shows the chat input and empty state', () => {
    const wrapper = mount(App)
    expect(wrapper.find('.chat-input').exists()).toBe(true)
    expect(wrapper.text()).toContain('描述你想完成的任务')
  })
})