/**
 * The SSE wire contract, mirroring `server/service/events.py`.
 *
 * The two files must change together: this is a cross-language boundary
 * that TypeScript cannot check for us, so the event-name list is
 * duplicated deliberately and pinned by a test on each side.
 */

export const EVENT_NAMES = [
  'thinking_delta',
  'text_delta',
  'tool_call_start',
  'tool_call_end',
  'artifact_created',
  'require_confirm',
  'task_renamed',
  'task_todos_changed',
  'system_reminder',
  'done',
] as const

export type EventName = (typeof EVENT_NAMES)[number]

export interface SystemReminderData {
  block_id: string
  source: string
  content: string
}

export interface ThinkingDeltaData {
  text: string
}

export interface TextDeltaData {
  text: string
}

export interface ToolCallStartData {
  call_id: string
  tool: string
  args: Record<string, unknown>
}

export interface ToolCallEndData {
  call_id: string
  status: 'success' | 'error'
  result_summary: string
}

export interface ArtifactCreatedData {
  type: 'html' | 'markdown' | 'image' | 'text'
  file_path: string
  url: string
}

export interface RequireConfirmData {
  reply_id: string
  command: string
  reason: string
  action: 'allow'
}

/**
 * Emitted once, right before the first reply of a brand-new task starts
 * streaming, when the backend has auto-generated a title from the
 * user's first message (see `server/service/title_generator.py`).
 * Not part of `AgentEventTranslator`'s AgentScope-event mirroring like
 * the others above — `main.py`'s `/api/chat` handler emits this one
 * directly, the same way it does for `artifact_created`.
 */
export interface TaskRenamedData {
  title: string
}

export interface DoneData {
  task_status: string
}

/**
 * A snapshot of the agent's internal todo list. See
 * `docs/specs/2026-09-28-todo-display.md` for the wire shape; the
 * backend emits one of these on every TaskCreate / TaskUpdate, plus one
 * unconditional snapshot at the end of every turn. The frontend treats
 * the payload as authoritative — it overwrites the previous list
 * rather than diffing.
 */
export interface TodoItem {
  id: string
  subject: string
  description: string
  state: 'pending' | 'in_progress' | 'completed' | 'deleted'
  owner: string | null
  blocks: string[]
  blockedBy: string[]
  createdAt: string
}

export interface TaskTodosChangedData {
  todos: TodoItem[]
}

export interface ParsedFrame {
  event: EventName
  data: Record<string, unknown>
}

const KNOWN = new Set<string>(EVENT_NAMES)

/**
 * Parse one complete SSE frame.
 *
 * @param frame - A frame terminated by a blank line.
 * @returns The parsed event, or `null` when the frame is malformed or
 *          carries an event name this client does not know about. Unknown
 *          names return null rather than throwing so a newer backend does
 *          not break an older UI.
 */
export function parseSseFrame(frame: string): ParsedFrame | null {
  const lines = frame.split('\n').filter((line) => line.length > 0)
  const eventLine = lines.find((line) => line.startsWith('event: '))
  const dataLine = lines.find((line) => line.startsWith('data: '))

  if (!eventLine || !dataLine) return null

  const event = eventLine.slice('event: '.length).trim()
  if (!KNOWN.has(event)) return null

  try {
    return {
      event: event as EventName,
      data: JSON.parse(dataLine.slice('data: '.length)),
    }
  } catch {
    return null
  }
}

/**
 * Split a streaming buffer into complete frames plus the trailing partial.
 *
 * SSE frames are delimited by a blank line. Chunks from the network arrive
 * at arbitrary boundaries, so a frame can be cut in half mid-JSON — the
 * remainder must be carried over to the next chunk rather than parsed.
 *
 * @param buffer - The accumulated raw text.
 * @returns The complete frames and the unconsumed remainder.
 */
export function splitSseBuffer(buffer: string): {
  frames: string[]
  rest: string
} {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  return { frames: parts.filter((part) => part.trim().length > 0), rest }
}