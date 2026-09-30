import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TodoPanel from '@/components/artifacts/TodoPanel.vue'
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
    description: '读取 yaml',
    state: 'in_progress',
    owner: 'explorer',
    blocks: [],
    blockedBy: ['1'],
    createdAt: '2026-09-30T10:00:01Z',
  },
  {
    id: '3',
    subject: '运行程序',
    description: '',
    state: 'pending',
    owner: null,
    blocks: [],
    blockedBy: [],
    createdAt: '2026-09-30T10:00:02Z',
  },
]

function mountPanel() {
  setActivePinia(createPinia())
  const store = useTodosStore()
  return { wrapper: mount(TodoPanel), store }
}

describe('TodoPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('shows an empty state when no todos exist', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.text()).toContain('暂无待办')
  })

  it('renders every todo subject', async () => {
    const { wrapper, store } = mountPanel()
    store.applyFrame({ todos: FIXTURE })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('读取配置')
    expect(wrapper.text()).toContain('解析配置')
    expect(wrapper.text()).toContain('运行程序')
  })

  it('shows the completion summary', async () => {
    const { wrapper, store } = mountPanel()
    store.applyFrame({ todos: FIXTURE })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('1 / 3')
  })

  it('renders the description when present', async () => {
    const { wrapper, store } = mountPanel()
    store.applyFrame({ todos: FIXTURE })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('读取 yaml')
  })

  it('shows blocked-by hint for tasks with dependencies', async () => {
    const { wrapper, store } = mountPanel()
    store.applyFrame({ todos: FIXTURE })
    await wrapper.vm.$nextTick()
    // Task 2 blocked by task 1 — text should reference the blocker id.
    expect(wrapper.text()).toContain('阻塞于 #1')
  })

  it('hides soft-deleted tasks by default', async () => {
    const { wrapper, store } = mountPanel()
    store.applyFrame({
      todos: [
        ...FIXTURE,
        {
          id: '99',
          subject: '已放弃的尝试',
          description: '',
          state: 'deleted',
          owner: null,
          blocks: [],
          blockedBy: [],
          createdAt: '2026-09-30T10:00:99Z',
        },
      ],
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('已放弃的尝试')
  })
})