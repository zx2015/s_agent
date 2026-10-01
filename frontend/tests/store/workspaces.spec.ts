import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from '@/store/workspaces'
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
      {
        id: 't2',
        title: '分析数据',
        workspaceId: 'w1',
        status: 'running',
        updatedAt: '2026-09-28T11:00:00Z',
        hasArtifacts: false,
      },
    ],
  },
  {
    id: 'w2',
    name: '项目 B',
    tasks: [
      {
        id: 't3',
        title: '写周报',
        workspaceId: 'w2',
        status: 'completed',
        updatedAt: '2026-09-27T09:00:00Z',
        hasArtifacts: false,
      },
    ],
  },
]

describe('workspace store', () => {
  let store: ReturnType<typeof useWorkspaceStore>

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useWorkspaceStore()
    // The store mutates the tree it is given (archiving splices, creating
    // unshifts), so each test needs its own copy — sharing one fixture
    // would let earlier tests silently change later tests' inputs.
    store.setWorkspaces(structuredClone(FIXTURE))
  })

  it('starts empty', () => {
    const fresh = useWorkspaceStore()
    fresh.setWorkspaces([])
    expect(fresh.workspaces).toEqual([])
  })

  it('loads workspaces', () => {
    expect(store.workspaces).toHaveLength(2)
  })

  it('filters tasks across all workspaces by title', () => {
    store.setSearchQuery('周报')
    expect(store.filteredWorkspaces).toHaveLength(1)
    expect(store.filteredWorkspaces[0].tasks).toHaveLength(1)
  })

  it('returns every workspace when the query is empty', () => {
    store.setSearchQuery('')
    expect(store.filteredWorkspaces).toHaveLength(2)
  })

  it('search is case-insensitive', () => {
    store.setSearchQuery('生成落地页')
    expect(store.filteredWorkspaces[0].tasks[0].id).toBe('t1')
  })

  it('selects a task and persists to localStorage and URL', () => {
    store.selectTask('t2')
    expect(store.activeTaskId).toBe('t2')
    expect(localStorage.getItem('s_agent_active_task_id')).toBe('t2')
    expect(window.location.search).toContain('taskId=t2')
  })

  it('restores activeTaskId from localStorage upon store creation', () => {
    setActivePinia(createPinia())
    localStorage.setItem('s_agent_active_task_id', 't1')
    const fresh = useWorkspaceStore()
    expect(fresh.activeTaskId).toBe('t1')
  })

  it('renames a task', () => {
    store.renameTask('t1', '新标题')
    expect(store.findTask('t1')?.title).toBe('新标题')
  })

  it('archives a task by removing it from the tree', () => {
    store.archiveTask('t1')
    expect(store.findTask('t1')).toBeUndefined()
  })

  it('clears a dangling active selection and storage when its task is archived', () => {
    // Otherwise the chat pane keeps rendering a task the sidebar no longer
    // shows, and the user has no way back to a consistent state.
    store.selectTask('t2')
    expect(localStorage.getItem('s_agent_active_task_id')).toBe('t2')
    store.archiveTask('t2')
    expect(store.activeTaskId).toBeNull()
    expect(localStorage.getItem('s_agent_active_task_id')).toBeNull()
    expect(window.location.search).not.toContain('taskId=t2')
  })

  it('creates a task in the given workspace', () => {
    const created = store.createTask('w2', '新任务')
    expect(created.title).toBe('新任务')
    expect(store.findTask(created.id)?.workspaceId).toBe('w2')
  })

  it('groups tasks under their workspace', () => {
    const workspace = store.filteredWorkspaces.find((w) => w.id === 'w1')
    expect(workspace?.tasks.map((t) => t.id)).toEqual(['t1', 't2'])
  })

  it('ignores a rename to an empty title', () => {
    store.renameTask('t1', '   ')
    expect(store.findTask('t1')?.title).toBe('生成落地页')
  })

  it('rejects creating a task in an unknown workspace', () => {
    expect(() => store.createTask('nope', 'x')).toThrow()
  })

  it('tracks activeTask as a resolved object', () => {
    store.selectTask('t3')
    expect(store.activeTask?.title).toBe('写周报')
  })

  it('marks a task as having artifacts', () => {
    store.markArtifacts('t2')
    expect(store.findTask('t2')?.hasArtifacts).toBe(true)
  })

  it('creates a workspace via the backend and adds it to the tree', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: 'w-new', name: '新工作区', tasks: [] }),
      }),
    )

    const workspace = await store.createWorkspaceRemote('新工作区')

    expect(workspace).toEqual({ id: 'w-new', name: '新工作区', tasks: [] })
    expect(store.workspaces.map((w) => w.id)).toContain('w-new')
  })

  it('deletes a workspace via the backend and removes it from the tree', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
    )

    await store.deleteWorkspaceRemote('w2')

    expect(fetch).toHaveBeenCalledWith(
      '/api/workspaces/w2',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(store.workspaces.map((w) => w.id)).not.toContain('w2')
  })

  it('clears the active task selection when its workspace is deleted', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
    )
    store.selectTask('t3')

    await store.deleteWorkspaceRemote('w2')

    expect(store.activeTaskId).toBeNull()
  })

  it('leaves the active task selection untouched when a different workspace is deleted', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
    )
    store.selectTask('t1')

    await store.deleteWorkspaceRemote('w2')

    expect(store.activeTaskId).toBe('t1')
  })
})