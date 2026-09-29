import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkspaceTree from '@/components/sidebar/WorkspaceTree.vue'
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
})