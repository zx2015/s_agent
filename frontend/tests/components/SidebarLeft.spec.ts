import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SidebarLeft from '@/components/sidebar/SidebarLeft.vue'
import { useWorkspaceStore } from '@/store/workspaces'

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('SidebarLeft', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('creates a workspace via the backend when a name is entered', async () => {
    vi.stubGlobal('prompt', vi.fn().mockReturnValue('新项目'))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: 'w-new', name: '新项目', tasks: [] }),
      }),
    )
    const wrapper = mount(SidebarLeft)
    const store = useWorkspaceStore()

    await wrapper.find('.new-workspace').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/workspaces',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(store.workspaces.map((w) => w.id)).toContain('w-new')
  })

  it('does nothing when the prompt is dismissed', async () => {
    vi.stubGlobal('prompt', vi.fn().mockReturnValue(null))
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(SidebarLeft)

    await wrapper.find('.new-workspace').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
  })

  it('does nothing for a blank workspace name', async () => {
    vi.stubGlobal('prompt', vi.fn().mockReturnValue('   '))
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(SidebarLeft)

    await wrapper.find('.new-workspace').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
  })
})
