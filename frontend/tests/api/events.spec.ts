import { describe, expect, it } from 'vitest'
import {
  EVENT_NAMES,
  parseSseFrame,
  splitSseBuffer,
} from '@/api/events'

describe('SSE contract', () => {
  it('lists exactly the events the backend can emit', () => {
    // Mirrors server/service/events.py::EVENT_NAMES. A drift here means
    // the UI silently ignores frames it should render.
    expect([...EVENT_NAMES].sort()).toEqual(
      [
        'artifact_created',
        'done',
        'require_confirm',
        'system_reminder',
        'task_renamed',
        'task_todos_changed',
        'text_delta',
        'thinking_delta',
        'tool_call_end',
        'tool_call_start',
      ].sort(),
    )
  })

  it('parses a system_reminder frame', () => {
    const frame =
      'event: system_reminder\ndata: {"block_id":"b1","source":"system","content":"时间: 2026-10-01"}\n\n'
    expect(parseSseFrame(frame)).toEqual({
      event: 'system_reminder',
      data: { block_id: 'b1', source: 'system', content: '时间: 2026-10-01' },
    })
  })

  it('parses a text_delta frame', () => {
    const frame = 'event: text_delta\ndata: {"text":"你好"}\n\n'
    expect(parseSseFrame(frame)).toEqual({
      event: 'text_delta',
      data: { text: '你好' },
    })
  })

  it('parses a tool_call_start frame', () => {
    const frame =
      'event: tool_call_start\ndata: {"call_id":"c1","tool":"calculate","args":{"expression":"1+1"}}\n\n'
    const parsed = parseSseFrame(frame)
    expect(parsed.event).toBe('tool_call_start')
    expect(parsed.data.tool).toBe('calculate')
  })

  it('parses a task_todos_changed frame with full todo items', () => {
    const payload = {
      todos: [
        {
          id: '1',
          subject: '读取配置',
          description: '',
          state: 'completed',
          owner: 'explorer',
          blocks: ['2'],
          blockedBy: [],
          createdAt: '2026-09-30T10:00:00Z',
        },
        {
          id: '2',
          subject: '解析配置',
          description: '',
          state: 'in_progress',
          owner: null,
          blocks: [],
          blockedBy: ['1'],
          createdAt: '2026-09-30T10:00:01Z',
        },
      ],
    }
    const frame = `event: task_todos_changed\ndata: ${JSON.stringify(payload)}\n\n`
    const parsed = parseSseFrame(frame)
    expect(parsed?.event).toBe('task_todos_changed')
    expect(parsed?.data.todos).toHaveLength(2)
    expect(parsed?.data.todos[0].state).toBe('completed')
    expect(parsed?.data.todos[1].blockedBy).toEqual(['1'])
  })

  it('parses an empty task_todos_changed frame as an empty list', () => {
    const frame = 'event: task_todos_changed\ndata: {"todos":[]}\n\n'
    const parsed = parseSseFrame(frame)
    expect(parsed?.event).toBe('task_todos_changed')
    expect(parsed?.data.todos).toEqual([])
  })

  it('returns null for an unknown event name', () => {
    // Forward compatibility: a newer backend must not crash the UI.
    const frame = 'event: future_event\ndata: {"x":1}\n\n'
    expect(parseSseFrame(frame)).toBeNull()
  })

  it('returns null for a malformed frame', () => {
    expect(parseSseFrame('event: text_delta\n')).toBeNull()
    expect(parseSseFrame('garbage')).toBeNull()
  })

  it('splits a buffer into complete frames and a remainder', () => {
    const buffer =
      'event: text_delta\ndata: {"text":"a"}\n\n' +
      'event: text_delta\ndata: {"text":"b"}\n\n' +
      'event: text_de'
    const { frames, rest } = splitSseBuffer(buffer)
    expect(frames).toHaveLength(2)
    expect(rest).toBe('event: text_de')
  })

  it('leaves an incomplete buffer untouched', () => {
    const { frames, rest } = splitSseBuffer('event: text_delta\ndata: {"text":"a"}')
    expect(frames).toHaveLength(0)
    expect(rest).toContain('text_delta')
  })
})