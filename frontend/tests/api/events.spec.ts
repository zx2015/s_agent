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
        'task_renamed',
        'text_delta',
        'thinking_delta',
        'tool_call_end',
        'tool_call_start',
      ].sort(),
    )
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