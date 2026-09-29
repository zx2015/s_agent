import { describe, expect, it } from 'vitest'
import { mockTurn } from '@/mock/sse-server'
import { parseSseFrame } from '@/api/events'

/** Resolve immediately: the delays exist for the UI, not for assertions. */
const noWait = () => Promise.resolve()

async function collect(message: string) {
  const frames: Array<{ event: string; data: Record<string, unknown> }> = []
  for await (const frame of mockTurn(message, noWait)) {
    const parsed = parseSseFrame(frame)
    if (parsed) frames.push(parsed)
  }
  return frames
}

describe('mockTurn', () => {
  it('emits a thinking chunk, text chunks, and a done event', async () => {
    const frames = await collect('你好')
    const names = frames.map((f) => f.event)
    expect(names).toContain('thinking_delta')
    expect(names).toContain('text_delta')
    expect(names[names.length - 1]).toBe('done')
  })

  it('echoes the user message in the reply', async () => {
    const frames = await collect('测试消息')
    const text = frames
      .filter((f) => f.event === 'text_delta')
      .map((f) => f.data.text as string)
      .join('')
    expect(text).toContain('测试消息')
  })

  it('emits a tool call pair for a shell-flavoured request', async () => {
    const frames = await collect('帮我执行 ls')
    const names = frames.map((f) => f.event)
    expect(names).toContain('tool_call_start')
    expect(names).toContain('tool_call_end')
  })

  it('emits an artifact event for a page request', async () => {
    const frames = await collect('帮我生成一个网页')
    expect(frames.map((f) => f.event)).toContain('artifact_created')
  })

  it('emits a confirm request for a dangerous command', async () => {
    const frames = await collect('删除所有文件')
    expect(frames.map((f) => f.event)).toContain('require_confirm')
  })

  it('produces only frames the real contract allows', async () => {
    // Every mock frame must survive the real parser, or the UI is being
    // developed against a contract the backend does not speak.
    for (const message of ['你好', '帮我执行 ls', '生成网页', '删除文件']) {
      for await (const frame of mockTurn(message, noWait)) {
        expect(parseSseFrame(frame)).not.toBeNull()
      }
    }
  })
})