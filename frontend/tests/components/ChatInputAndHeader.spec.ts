import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatInput from '@/components/chat/ChatInput.vue'
import TaskHeaderBar from '@/components/chat/TaskHeaderBar.vue'
import { useWorkspaceStore } from '@/store/workspaces'

describe('ChatInput', () => {
  it('disables the send button when input is whitespace only', () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    expect(wrapper.find('.send-button').attributes('disabled')).toBeDefined()
  })

  it('emits send with trimmed text on submit', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('  你好世界  ')
    await wrapper.find('.send-button').trigger('click')
    expect(wrapper.emitted('send')?.[0]).toEqual(['你好世界'])
  })

  it('shows a stop button when streaming', () => {
    const wrapper = mount(ChatInput, { props: { disabled: true } })
    expect(wrapper.text()).toContain('停止生成')
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