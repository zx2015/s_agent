import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '@/store/session'
import type { ParsedFrame } from '@/api/events'

function frame(event: string, data: Record<string, unknown>): ParsedFrame {
  return { event: event as ParsedFrame['event'], data }
}

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with no messages', () => {
    const store = useSessionStore()
    expect(store.messages).toHaveLength(0)
  })

  it('appends a user message', () => {
    const store = useSessionStore()
    store.addUserMessage('你好')
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('user')
    expect(store.messages[0].text).toBe('你好')
  })

  it('creates an empty assistant message for the turn', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('assistant')
    expect(store.messages[0].streaming).toBe(true)
  })

  it('accumulates text deltas into the assistant message', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('text_delta', { text: '你' }))
    store.applyFrame(frame('text_delta', { text: '好' }))
    expect(store.messages[0].text).toBe('你好')
  })

  it('accumulates thinking deltas separately from answer text', () => {
    // Thinking must not leak into the answer: it is rendered collapsed and
    // a user reading the transcript should not see reasoning inline.
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('thinking_delta', { text: '想' }))
    store.applyFrame(frame('text_delta', { text: '答' }))
    expect(store.messages[0].thinking).toBe('想')
    expect(store.messages[0].text).toBe('答')
  })

  it('strips <think> tags the model inlines into answer text', () => {
    // v-flash emits reasoning wrapped in <think>…</think> inside the text
    // stream; verified against the live model on 2026-09-28.
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('text_delta', { text: '<think>推理中</think>正式回答' }))
    expect(store.messages[0].text).toBe('正式回答')
    expect(store.messages[0].thinking).toContain('推理中')
  })

  it('keeps a think block split across chunks out of the answer', () => {
    // Streaming splits the tag at arbitrary points. Without remembering
    // that we are mid-think, the closing tag leaks into the answer text
    // and the user sees raw markup.
    const OPEN = '<think>'
    const CLOSE = '</think>'
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('text_delta', { text: `before ${OPEN}abc` }))
    store.applyFrame(frame('text_delta', { text: `def${CLOSE}after` }))
    expect(store.messages[0].text).toBe('before after')
    expect(store.messages[0].thinking).toBe('abcdef')
  })

  it('handles two think blocks in one turn', () => {
    const OPEN = '<think>'
    const CLOSE = '</think>'
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(
      frame('text_delta', { text: `a ${OPEN}1${CLOSE}b ${OPEN}2${CLOSE}c` }),
    )
    expect(store.messages[0].text).toBe('a b c')
    expect(store.messages[0].thinking).toBe('12')
  })

  it('records a tool call and its completion', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(
      frame('tool_call_start', {
        call_id: 'c1',
        tool: 'calculate',
        args: { expression: '1+1' },
      }),
    )
    expect(store.messages[0].toolCalls).toHaveLength(1)
    expect(store.messages[0].toolCalls[0].status).toBe('running')

    store.applyFrame(
      frame('tool_call_end', {
        call_id: 'c1',
        status: 'success',
        result_summary: '2',
      }),
    )
    expect(store.messages[0].toolCalls[0].status).toBe('success')
    expect(store.messages[0].toolCalls[0].summary).toBe('2')
  })

  it('records system reminders on the assistant message', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(
      frame('system_reminder', {
        block_id: 'b1',
        source: 'system',
        content: '当前时间为 2026-10-01',
      }),
    )
    expect(store.messages[0].systemReminders).toHaveLength(1)
    expect(store.messages[0].systemReminders?.[0]).toEqual({
      blockId: 'b1',
      source: 'system',
      content: '当前时间为 2026-10-01',
    })
  })

  it('marks the turn finished on done', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('done', { task_status: 'completed' }))
    expect(store.messages[0].streaming).toBe(false)
  })

  it('records a pending confirmation request', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('require_confirm', {
        reply_id: 'r1',
        command: 'rm -rf build',
        reason: '高危',
        action: 'allow',
      }),
    )
    expect(store.pendingConfirm?.replyId).toBe('r1')
  })

  it('clears the pending confirmation once resolved', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('require_confirm', {
        reply_id: 'r1',
        command: 'rm -rf build',
        reason: '高危',
        action: 'allow',
      }),
    )
    store.resolveConfirm('allow')
    expect(store.pendingConfirm).toBeNull()
  })

  it('collects artifacts announced during the turn', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('artifact_created', {
        type: 'html',
        file_path: 'index.html',
        url: '/api/tasks/t1/artifacts/preview/index.html',
      }),
    )
    expect(store.artifacts).toHaveLength(1)
    expect(store.artifacts[0].filePath).toBe('index.html')
  })

  it('deduplicates artifacts by path', () => {
    const store = useSessionStore()
    const payload = {
      type: 'html',
      file_path: 'index.html',
      url: '/api/tasks/t1/artifacts/preview/index.html',
    }
    store.applyFrame(frame('artifact_created', payload))
    store.applyFrame(frame('artifact_created', payload))
    expect(store.artifacts).toHaveLength(1)
  })

  it('resets the session on task switch', () => {
    const store = useSessionStore()
    store.addUserMessage('旧消息')
    store.reset()
    expect(store.messages).toHaveLength(0)
    expect(store.artifacts).toHaveLength(0)
  })

  it('ignores any frame when no turn is open', () => {
    // Frames can arrive after a reset; applying them would corrupt state.
    const store = useSessionStore()
    store.applyFrame(frame('text_delta', { text: '孤儿' }))
    expect(store.messages).toHaveLength(0)
  })

  describe('loadHistory', () => {
    beforeEach(() => {
      vi.restoreAllMocks()
    })

    it('replaces the current transcript with the server response', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            messages: [
              { id: 'h1', role: 'user', text: '旧用户', thinking: '', toolCalls: [], streaming: false },
              {
                id: 'h2',
                role: 'assistant',
                text: '旧回答',
                thinking: '旧思考',
                toolCalls: [],
                streaming: false,
              },
            ],
          }),
        }),
      )
      const store = useSessionStore()
      store.addUserMessage('当前会话的临时消息')
      store.applyFrame(frame('text_delta', { text: '临时回答' }))

      await store.loadHistory('t1')

      expect(store.messages).toHaveLength(2)
      expect(store.messages[0].text).toBe('旧用户')
      expect(store.messages[1].text).toBe('旧回答')
      expect(store.messages[1].thinking).toBe('旧思考')
      expect(store.isStreaming).toBe(false)
    })

    it('clears the conversation when the endpoint returns no messages', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ messages: [] }),
        }),
      )
      const store = useSessionStore()
      store.addUserMessage('占位')

      await store.loadHistory('t1')

      expect(store.messages).toEqual([])
      expect(store.pendingConfirm).toBeNull()
    })

    it('falls back to an empty transcript when the endpoint errors', async () => {
      // A failed hydrate must not leave the UI in a half-loaded state.
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: false,
          status: 500,
          text: async () => 'boom',
        }),
      )
      const store = useSessionStore()
      store.addUserMessage('占位')

      await store.loadHistory('t1')

      expect(store.messages).toEqual([])
    })

    it('targets the right URL', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [] }),
      })
      vi.stubGlobal('fetch', fetchMock)

      const store = useSessionStore()
      await store.loadHistory('abc')

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/tasks/abc/messages',
        expect.objectContaining({ headers: expect.any(Object) }),
      )
    })
  })
})