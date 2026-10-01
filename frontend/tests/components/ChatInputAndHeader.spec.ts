import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { McInput } from '@matechat/core'
import ChatInput from '@/components/chat/ChatInput.vue'
import TaskHeaderBar from '@/components/chat/TaskHeaderBar.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'

describe('ChatInput', () => {
  it('does not emit send for whitespace-only input', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    await wrapper.findComponent(McInput).vm.$emit('submit', '   ')
    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('emits send with trimmed text on submit', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    await wrapper.findComponent(McInput).vm.$emit('submit', '  你好世界  ')
    expect(wrapper.emitted('send')?.[0]).toEqual(['你好世界'])
  })

  it('puts McInput into its loading/cancel state while streaming', () => {
    const wrapper = mount(ChatInput, { props: { disabled: true } })
    expect(wrapper.findComponent(McInput).props('loading')).toBe(true)
  })

  it('emits stop when McInput cancels', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: true } })
    await wrapper.findComponent(McInput).vm.$emit('cancel')
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })
})

describe('TaskHeaderBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('displays the active task title and workspace tags', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces([
      {
        id: 'w1',
        name: '工作区Alpha',
        tasks: [
          {
            id: 't1',
            title: '测试任务',
            workspaceId: 'w1',
            workspacePath: '/workspaces/t1',
            status: 'running',
            updatedAt: '',
            hasArtifacts: false,
          },
        ],
      },
    ])
    store.selectTask('t1')

    const wrapper = mount(TaskHeaderBar)
    expect(wrapper.text()).toContain('测试任务')
    expect(wrapper.text()).toContain('工作区Alpha')
    expect(wrapper.text()).toContain('/workspaces/t1')
  })

  it('shows placeholder when no task is selected', () => {
    const wrapper = mount(TaskHeaderBar)
    expect(wrapper.text()).toContain('未选择任务')
  })

  it('shows stop button when session is streaming', async () => {
    const session = useSessionStore()
    const store = useWorkspaceStore()
    store.setWorkspaces([
      {
        id: 'w1',
        name: 'W',
        tasks: [
          {
            id: 't1',
            title: '运行中的任务',
            workspaceId: 'w1',
            status: 'running',
            updatedAt: '',
            hasArtifacts: false,
          },
        ],
      },
    ])
    store.selectTask('t1')

    const wrapper = mount(TaskHeaderBar)
    expect(wrapper.find('.action-danger').exists()).toBe(false)

    session.beginAssistantTurn()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.action-danger').exists()).toBe(true)
    expect(wrapper.find('.action-danger').text()).toContain('强制中断')
  })

  it('calls archiveTaskRemote when archive button is clicked', async () => {
    const store = useWorkspaceStore()
    store.setWorkspaces([
      {
        id: 'w1',
        name: 'W',
        tasks: [
          {
            id: 't1',
            title: '待归档任务',
            workspaceId: 'w1',
            status: 'running',
            updatedAt: '',
            hasArtifacts: false,
          },
        ],
      },
    ])
    store.selectTask('t1')

    const archiveSpy = vi.spyOn(store, 'archiveTaskRemote').mockResolvedValue()
    const wrapper = mount(TaskHeaderBar)
    const buttons = wrapper.findAll('.action')
    const archiveBtn = buttons.find((b) => b.text().includes('归档'))
    expect(archiveBtn).toBeDefined()
    await archiveBtn?.trigger('click')
    expect(archiveSpy).toHaveBeenCalledWith('t1')
  })

  it('calls resetTaskContextRemote and session.reset on clear context', async () => {
    const store = useWorkspaceStore()
    const session = useSessionStore()
    store.setWorkspaces([
      {
        id: 'w1',
        name: 'W',
        tasks: [
          {
            id: 't1',
            title: '清空记忆任务',
            workspaceId: 'w1',
            status: 'running',
            updatedAt: '',
            hasArtifacts: false,
          },
        ],
      },
    ])
    store.selectTask('t1')

    const resetSpy = vi.spyOn(store, 'resetTaskContextRemote').mockResolvedValue()
    const sessionSpy = vi.spyOn(session, 'reset')
    const wrapper = mount(TaskHeaderBar)
    const buttons = wrapper.findAll('.action')
    const clearBtn = buttons.find((b) => b.text().includes('清空上下文'))
    expect(clearBtn).toBeDefined()
    await clearBtn?.trigger('click')
    expect(resetSpy).toHaveBeenCalledWith('t1')
    expect(sessionSpy).toHaveBeenCalled()
  })
})