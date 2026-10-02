import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MessageList from '@/components/chat/MessageList.vue'
import { useSessionStore } from '@/store/session'
import type { ParsedFrame } from '@/api/events'

function mountList() {
  setActivePinia(createPinia())
  const store = useSessionStore()
  return { wrapper: mount(MessageList), store }
}

describe('MessageList', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders user messages', async () => {
    const { wrapper, store } = mountList()
    store.addUserMessage('帮我做件事')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('帮我做件事')
  })

  it('renders assistant text', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({ event: 'text_delta', data: { text: '好的' } } as ParsedFrame)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('好的')
  })

  it('renders a tool call card', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({
      event: 'tool_call_start',
      data: { call_id: 'c1', tool: 'calculate', args: {} },
    } as ParsedFrame)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('calculate')
  })

  it('renders the confirmation card when a confirm is pending', async () => {
    const { wrapper, store } = mountList()
    store.applyFrame({
      event: 'require_confirm',
      data: {
        reply_id: 'r1',
        command: 'rm -rf build',
        reason: '高危',
        action: 'allow',
      },
    } as ParsedFrame)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('rm -rf build')
  })

  it('shows an empty state before any message', () => {
    const { wrapper } = mountList()
    expect(wrapper.find('[data-test="empty-state"]').exists()).toBe(true)
  })

  it('hides the empty state once a message exists', async () => {
    const { wrapper, store } = mountList()
    store.addUserMessage('嗨')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="empty-state"]').exists()).toBe(false)
  })

  it('renders a collapsed thinking block separately from the answer', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({
      event: 'thinking_delta',
      data: { text: '推理过程' },
    } as ParsedFrame)
    store.applyFrame({ event: 'text_delta', data: { text: '答案' } } as ParsedFrame)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('思考过程')
    expect(wrapper.find('[data-test="assistant-text"]').text()).toBe('答案')
  })

  it('renders interleaved blocks in chronological order', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({ event: 'text_delta', data: { text: '前置说明' } } as ParsedFrame)
    store.applyFrame({
      event: 'tool_call_start',
      data: { call_id: 'c1', tool: 'delegate_task', args: { role: '分析师' } },
    } as ParsedFrame)
    store.applyFrame({ event: 'text_delta', data: { text: '后置总结' } } as ParsedFrame)
    await wrapper.vm.$nextTick()

    const textElements = wrapper.findAll('[data-test="assistant-text"]')
    expect(textElements.length).toBe(2)
    expect(textElements[0].text()).toContain('前置说明')
    expect(textElements[1].text()).toContain('后置总结')
    expect(wrapper.text()).toContain('子智能体委派 (分析师)')
  })

  it('renders history loader button when hasMoreHistory is true and handles click', async () => {
    const { wrapper, store } = mountList()
    expect(wrapper.find('[data-test="history-loader"]').exists()).toBe(false)

    // Set hasMoreHistory
    store.addUserMessage('当前消息')
    store.hasMoreHistory = true
    store.totalHistoryCount = 5
    await wrapper.vm.$nextTick()

    const loader = wrapper.find('[data-test="history-loader"]')
    expect(loader.exists()).toBe(true)
    expect(loader.text()).toContain('加载更早历史消息 (还有 4 条)')

    // Clicking button triggers loadMoreHistory
    let loadCalled = false
    store.loadMoreHistory = async () => {
      loadCalled = true
      return true
    }
    await wrapper.find('[data-test="load-more-btn"]').trigger('click')
    expect(loadCalled).toBe(true)
  })
})