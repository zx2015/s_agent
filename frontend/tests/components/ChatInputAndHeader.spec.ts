import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { McInput } from '@matechat/core'
import ChatInput from '@/components/chat/ChatInput.vue'
import TaskHeaderBar from '@/components/chat/TaskHeaderBar.vue'
import { useWorkspaceStore } from '@/store/workspaces'

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

  it('displays the active task title', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces([
      {
        id: 'w1',
        name: 'W',
        tasks: [
          {
            id: 't1',
            title: '测试任务',
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
    expect(wrapper.text()).toContain('测试任务')
  })

  it('shows placeholder when no task is selected', () => {
    const wrapper = mount(TaskHeaderBar)
    expect(wrapper.text()).toContain('未选择任务')
  })
})