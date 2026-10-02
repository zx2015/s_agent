/** Shared domain types for the workbench UI. */

export type TaskStatus = 'running' | 'completed' | 'suspended' | 'failed'

export interface Task {
  id: string
  title: string
  workspaceId: string
  status: TaskStatus
  updatedAt: string
  hasArtifacts: boolean
  isArchived?: boolean
  workspacePath?: string
}

export interface Workspace {
  id: string
  name: string
  tasks: Task[]
}

export interface SystemReminder {
  blockId: string
  source: string
  content: string
}

export type ChatContentBlock =
  | { type: 'thinking'; content: string }
  | { type: 'text'; content: string }
  | { type: 'tool_call'; call: ToolCallRecord }
  | { type: 'system_reminder'; blockId: string; content: string }

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  /** Visible answer text. */
  text: string
  /** The model's reasoning, rendered in a collapsed block. */
  thinking: string
  /** Tool invocations in this turn, in order. */
  toolCalls: ToolCallRecord[]
  /** System reminders (e.g. environment block, time, memory hints) */
  systemReminders?: SystemReminder[]
  /** Chronologically ordered interleaved content blocks (thinking, text, tool_call). */
  blocks?: ChatContentBlock[]
  /** Set while the turn is still streaming. */
  streaming: boolean
}

export interface MessagesResponse {
  messages: ChatMessage[]
  has_more: boolean
  total: number
}

export interface ToolCallRecord {
  callId: string
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'success' | 'error'
  summary: string
}

export interface PendingConfirm {
  replyId: string
  command: string
  reason: string
}

export interface Artifact {
  type: 'html' | 'markdown' | 'image' | 'text'
  filePath: string
  url: string
}

export interface ModelSettings {
  modelName: string
  baseUrl: string
}

export type TodoState = 'pending' | 'in_progress' | 'completed' | 'deleted'

/**
 * Mirror of `server/service/history.py::serialize_todos`. The backend
 * owns the truth (the agent's `AgentState.tasks_context.tasks`); the
 * frontend re-receives the full list on every `task_todos_changed`
 * SSE frame and replaces its local copy wholesale.
 */
export interface TodoItem {
  id: string
  subject: string
  description: string
  state: TodoState
  owner: string | null
  blocks: string[]
  blockedBy: string[]
  createdAt: string
}