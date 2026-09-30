import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkspaceTree from '@/components/sidebar/WorkspaceTree.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'
import type { Workspace } from '@/types'

const FIXTURE: Workspace[] = [
  {
    id: 'w1',
    name: '项目 A',
    tasks: [
      {
        id: 't1',
        title: '生成落地页',
        workspaceId: 'w1',
        status: 'completed',
        updatedAt: '2026-09-28T10:00:00Z',
        hasArtifacts: true,
      },
    ],
  },
]

function mountTree() {
  setActivePinia(createPinia())
  const store = useWorkspaceStore()
  store.setWorkspaces(structuredClone(FIXTURE))
  return { wrapper: mount(WorkspaceTree), store }
}

describe('WorkspaceTree', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders each workspace as a group', () => {
    const { wrapper } = mountTree()
    expect(wrapper.text()).toContain('项目 A')
  })

  it('renders the tasks inside a group', () => {
    const { wrapper } = mountTree()
    expect(wrapper.text()).toContain('生成落地页')
  })

  it('selects a task on click', async () => {
    const { wrapper, store } = mountTree()
    await wrapper.find('[data-test="task-t1"]').trigger('click')
    expect(store.activeTaskId).toBe('t1')
  })

  it('shows no tasks when the search excludes them', async () => {
    const { wrapper, store } = mountTree()
    store.setSearchQuery('不存在的内容')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('生成落地页')
  })

  it('marks the active task', async () => {
    const { wrapper, store } = mountTree()
    store.selectTask('t1')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="task-t1"]').classes()).toContain('active')
  })

  it('shows an artifact badge when the task has artifacts', () => {
    const { wrapper } = mountTree()
    expect(wrapper.find('[data-test="artifact-badge-t1"]').exists()).toBe(true)
  })

  it('does nothing when the delete confirm dialog is dismissed', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
    vi.stubGlobal('fetch', vi.fn())
    const { wrapper, store } = mountTree()

    await wrapper.find('[data-test="delete-task-t1"]').trigger('click')
    await flushPromises()

    expect(store.findTask('t1')).toBeDefined()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('deletes the task via the backend when confirmed', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }),
    )
    const { wrapper, store } = mountTree()

    await wrapper.find('[data-test="delete-task-t1"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/tasks/t1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(store.findTask('t1')).toBeUndefined()
  })

  it('clears the session when deleting the active task', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }),
    )
    const { wrapper, store } = mountTree()
    store.selectTask('t1')
    const session = useSessionStore()
    session.addUserMessage('嗨')

    await wrapper.find('[data-test="delete-task-t1"]').trigger('click')
    await flushPromises()

    expect(store.activeTaskId).toBeNull()
    expect(session.messages).toHaveLength(0)
  })

  it('deleting a non-active task leaves the current session untouched', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }),
    )
    const { wrapper, store } = mountTree()
    store.selectTask('other-task')
    const session = useSessionStore()
    session.addUserMessage('别删我')

    await wrapper.find('[data-test="delete-task-t1"]').trigger('click')
    await flushPromises()

    expect(store.activeTaskId).toBe('other-task')
    expect(session.messages).toHaveLength(1)
  })

  it('creates a task in a specific workspace via its "+" button', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 't-new',
          title: '新任务',
          workspaceId: 'w1',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      }),
    )
    const { wrapper, store } = mountTree()

    await wrapper.find('[data-test="new-task-in-w1"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(store.activeTaskId).toBe('t-new')
    expect(store.findTask('t-new')?.workspaceId).toBe('w1')
  })

  it("clicking a workspace's + button does not also toggle its collapse state", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 't-new',
          title: '新任务',
          workspaceId: 'w1',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      }),
    )
    const { wrapper } = mountTree()

    await wrapper.find('[data-test="new-task-in-w1"]').trigger('click')
    await flushPromises()

    // The original task is still visible, i.e. the group did not collapse.
    expect(wrapper.text()).toContain('生成落地页')
  })

  it('deletes a workspace and all its tasks after confirming, and resets the session if the active task was inside it', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
    const { wrapper, store } = mountTree()
    const session = useSessionStore()
    store.selectTask('t1')
    session.messages.push({
      id: 'm1',
      role: 'user',
      text: '嗨',
      thinking: '',
      toolCalls: [],
      streaming: false,
    })

    await wrapper.find('[data-test="delete-workspace-w1"]').trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining('1 个对话'),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/workspaces/w1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(store.workspaces.find((ws) => ws.id === 'w1')).toBeUndefined()
    expect(session.messages).toHaveLength(0)
  })

  it('does not call the backend when the delete-workspace confirmation is dismissed', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
    vi.stubGlobal('fetch', vi.fn())
    const { wrapper, store } = mountTree()

    await wrapper.find('[data-test="delete-workspace-w1"]').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
    expect(store.workspaces.find((ws) => ws.id === 'w1')).toBeDefined()
  })

  it("clicking a workspace's delete button does not also toggle its collapse state or select a task", async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
    const { wrapper } = mountTree()

    await wrapper.find('[data-test="delete-workspace-w1"]').trigger('click')

    // The group is still expanded and untouched, i.e. the click was
    // isolated to the delete action.
    expect(wrapper.text()).toContain('生成落地页')
  })

  it('does not render a delete button for the default workspace', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces([
      { id: 'default', name: '默认工作区', tasks: [] },
      ...structuredClone(FIXTURE),
    ])
    const wrapper = mount(WorkspaceTree)

    expect(wrapper.find('[data-test="delete-workspace-default"]').exists()).toBe(
      false,
    )
    expect(wrapper.find('[data-test="delete-workspace-w1"]').exists()).toBe(
      true,
    )
  })
})

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}