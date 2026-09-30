import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SidebarLeft from '@/components/sidebar/SidebarLeft.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import type { Workspace } from '@/types'

const FIXTURE: Workspace[] = [
  { id: 'default', name: '默认工作区', tasks: [] },
  { id: 'w2', name: '项目 B', tasks: [] },
]

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

function mountSidebar() {
  setActivePinia(createPinia())
  const store = useWorkspaceStore()
  store.setWorkspaces(structuredClone(FIXTURE))
  return { wrapper: mount(SidebarLeft), store }
}

describe('SidebarLeft', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('opens an in-page creation panel instead of a native prompt', async () => {
    const { wrapper } = mountSidebar()
    expect(wrapper.find('[data-test="create-panel"]').exists()).toBe(false)

    await wrapper.find('.new-task').trigger('click')

    expect(wrapper.find('[data-test="create-panel"]').exists()).toBe(true)
  })

  it('creates a task in the selected existing workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 't-new',
          title: '新任务',
          workspaceId: 'w2',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      }),
    )
    const { wrapper, store } = mountSidebar()

    await wrapper.find('.new-task').trigger('click')
    await wrapper.find('[data-test="new-task-workspace"]').setValue('w2')
    await wrapper.find('[data-test="confirm-create"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ workspaceId: 'w2', title: '新任务' }),
      }),
    )
    expect(store.activeTaskId).toBe('t-new')
    expect(wrapper.find('[data-test="create-panel"]').exists()).toBe(false)
  })

  it('uses the entered title instead of the default when given one', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 't-new',
          title: '写周报',
          workspaceId: 'default',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      }),
    )
    const { wrapper } = mountSidebar()

    await wrapper.find('.new-task').trigger('click')
    await wrapper.find('[data-test="new-task-title"]').setValue('写周报')
    await wrapper.find('[data-test="confirm-create"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({
        body: JSON.stringify({ workspaceId: 'default', title: '写周报' }),
      }),
    )
  })

  it('creates a new folder first, then the task inside it, when "+ 新建文件夹" is chosen', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'w-new', name: '股票分析', tasks: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 't-new',
          title: '新任务',
          workspaceId: 'w-new',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper, store } = mountSidebar()

    await wrapper.find('.new-task').trigger('click')
    await wrapper.find('[data-test="new-task-workspace"]').setValue('__new__')
    await wrapper.find('[data-test="new-workspace-name"]').setValue('股票分析')
    await wrapper.find('[data-test="confirm-create"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/workspaces',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: '股票分析' }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/tasks',
      expect.objectContaining({
        body: JSON.stringify({ workspaceId: 'w-new', title: '新任务' }),
      }),
    )
    expect(store.workspaces.map((w) => w.id)).toContain('w-new')
    expect(store.activeTaskId).toBe('t-new')
  })

  it('disables the confirm button until a new folder name is entered', async () => {
    const { wrapper } = mountSidebar()

    await wrapper.find('.new-task').trigger('click')
    await wrapper.find('[data-test="new-task-workspace"]').setValue('__new__')

    expect(
      wrapper.find('[data-test="confirm-create"]').attributes('disabled'),
    ).toBeDefined()

    await wrapper.find('[data-test="new-workspace-name"]').setValue('新文件夹')

    expect(
      wrapper.find('[data-test="confirm-create"]').attributes('disabled'),
    ).toBeUndefined()
  })

  it('closes the panel without creating anything on cancel', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const { wrapper } = mountSidebar()

    await wrapper.find('.new-task').trigger('click')
    await wrapper.find('.panel-cancel').trigger('click')

    expect(wrapper.find('[data-test="create-panel"]').exists()).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
  })
})
