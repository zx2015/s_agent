/** Shared domain types for the workbench UI. */

export type TaskStatus = 'running' | 'completed' | 'suspended' | 'failed'

export interface Task {
  id: string
  title: string
  workspaceId: string
  status: TaskStatus
  updatedAt: string
  hasArtifacts: boolean
}

export interface Workspace {
  id: string
  name: string
  tasks: Task[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  /** Visible answer text. */
  text: string
  /** The model's reasoning, rendered in a collapsed block. */
  thinking: string
  /** Tool invocations in this turn, in order. */
  toolCalls: ToolCallRecord[]
  /** Set while the turn is still streaming. */
  streaming: boolean
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