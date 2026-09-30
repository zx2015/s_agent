import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTodosStore } from '@/store/todos'
import type { TodoItem } from '@/types'

const FIXTURE: TodoItem[] = [
  {
    id: '1',
    subject: '读取配置',
    description: '',
    state: 'completed',
    owner: null,
    blocks: ['2'],
    blockedBy: [],
    createdAt: '2026-09-30T10:00:00Z',
  },
  {
    id: '2',
    subject: '解析配置',
    description: '',
    state: 'in_progress',
    owner: 'explorer',
    blocks: [],
    blockedBy: ['1'],
    createdAt: '2026-09-30T10:00:01Z',
  },
]

describe('todos store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('starts empty', () => {
    const store = useTodosStore()
    expect(store.todos).toEqual([])
  })

  it('targets the right URL on loadTodos', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ todos: FIXTURE }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useTodosStore()
    await store.loadTodos('t1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/tasks/t1/todos',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('replaces the todo list with the server response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ todos: FIXTURE }),
      }),
    )
    const store = useTodosStore()
    await store.loadTodos('t1')
    expect(store.todos).toEqual(FIXTURE)
    expect(store.todos).toHaveLength(2)
  })

  it('falls back to an empty list when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'task not found',
      }),
    )
    const store = useTodosStore()
    await store.loadTodos('missing')
    expect(store.todos).toEqual([])
  })

  it('falls back to an empty list when the network throws', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('network down')),
    )
    const store = useTodosStore()
    await store.loadTodos('t1')
    expect(store.todos).toEqual([])
  })

  it('applyFrame replaces the entire list wholesale', () => {
    const store = useTodosStore()
    store.applyFrame({ todos: FIXTURE })
    expect(store.todos).toEqual(FIXTURE)
    // Apply a smaller list — the old entries must not be merged.
    store.applyFrame({ todos: FIXTURE.slice(0, 1) })
    expect(store.todos).toHaveLength(1)
  })

  it('clear empties the list', () => {
    const store = useTodosStore()
    store.applyFrame({ todos: FIXTURE })
    store.clear()
    expect(store.todos).toEqual([])
  })
})