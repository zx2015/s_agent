/**
 * The conversation state for the middle pane.
 *
 * Two pieces of real-world handling live here rather than in components:
 *
 * 1. `<think>` unwrapping. The `v-flash` model streams its reasoning
 *    wrapped in `<think>…</think>` inside the text channel (verified
 *    against the live model on 2026-09-28). Leaving those tags in the
 *    transcript would show raw markup to the user.
 * 2. Multi-session caching & turn guarding. Conversations are cached
 *    per-task so switching tasks preserves in-flight streams, prevents
 *    cross-task state leaks, and restores the view smoothly.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient } from '@/api/client'
import { useWorkspaceStore } from '@/store/workspaces'
import type { ParsedFrame } from '@/api/events'
import type { Artifact, ChatMessage, PendingConfirm, ToolCallRecord } from '@/types'

let messageCounter = 0

function newMessageId(): string {
  messageCounter += 1
  return `msg-${Date.now()}-${messageCounter}`
}

const THINK_OPEN = '<think>'
const THINK_CLOSE = '</think>'
const DEFAULT_TASK_ID = '__default__'

export interface TaskSessionState {
  messages: ChatMessage[]
  artifacts: Artifact[]
  pendingConfirm: PendingConfirm | null
  turnOpen: boolean
  insideThink: boolean
}

function createInitialSession(): TaskSessionState {
  return {
    messages: [],
    artifacts: [],
    pendingConfirm: null,
    turnOpen: false,
    insideThink: false,
  }
}

export const useSessionStore = defineStore('session', () => {
  const workspace = useWorkspaceStore()
  const currentTaskId = ref<string>(DEFAULT_TASK_ID)
  const taskSessions = ref<Record<string, TaskSessionState>>({
    [DEFAULT_TASK_ID]: createInitialSession(),
  })

  function resolveTaskId(targetTaskId?: string): string {
    return targetTaskId || workspace.activeTaskId || currentTaskId.value || DEFAULT_TASK_ID
  }

  function ensureSession(taskId: string): TaskSessionState {
    if (!taskSessions.value[taskId]) {
      taskSessions.value[taskId] = createInitialSession()
    }
    return taskSessions.value[taskId]
  }

  function getActiveSession(): TaskSessionState {
    const id = resolveTaskId()
    return ensureSession(id)
  }

  const messages = computed<ChatMessage[]>({
    get: () => getActiveSession().messages,
    set: (val: ChatMessage[]) => {
      getActiveSession().messages = val
    },
  })

  const artifacts = computed<Artifact[]>({
    get: () => getActiveSession().artifacts,
    set: (val: Artifact[]) => {
      getActiveSession().artifacts = val
    },
  })

  const pendingConfirm = computed<PendingConfirm | null>({
    get: () => getActiveSession().pendingConfirm,
    set: (val: PendingConfirm | null) => {
      getActiveSession().pendingConfirm = val
    },
  })

  const isStreaming = computed(() => getActiveSession().turnOpen)

  /** The assistant message currently being streamed for the active task, if any. */
  const currentAssistant = computed<ChatMessage | null>(() => {
    const msgs = messages.value
    const last = msgs[msgs.length - 1]
    return last && last.role === 'assistant' && last.streaming ? last : null
  })

  function switchToTask(taskId: string): void {
    currentTaskId.value = taskId
    ensureSession(taskId)
  }

  function hasMessages(taskId: string): boolean {
    return Boolean(taskSessions.value[taskId]?.messages.length)
  }

  function isTaskStreaming(taskId: string): boolean {
    return Boolean(taskSessions.value[taskId]?.turnOpen)
  }

  function appendThinkingBlock(message: ChatMessage, chunk: string): void {
    if (!chunk) return
    if (!message.blocks) message.blocks = []
    const last = message.blocks[message.blocks.length - 1]
    if (last && last.type === 'thinking') {
      last.content += chunk
    } else {
      message.blocks.push({ type: 'thinking', content: chunk })
    }
  }

  function appendTextBlock(message: ChatMessage, chunk: string): void {
    if (!chunk) return
    if (!message.blocks) message.blocks = []
    const last = message.blocks[message.blocks.length - 1]
    if (last && last.type === 'text') {
      last.content += chunk
    } else {
      message.blocks.push({ type: 'text', content: chunk })
    }
  }

  function addUserMessage(text: string, taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    const s = ensureSession(targetTaskId)
    s.messages.push({
      id: newMessageId(),
      role: 'user',
      text,
      thinking: '',
      toolCalls: [],
      blocks: [{ type: 'text', content: text }],
      streaming: false,
    })
  }

  function beginAssistantTurn(taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    const s = ensureSession(targetTaskId)
    s.messages.push({
      id: newMessageId(),
      role: 'assistant',
      text: '',
      thinking: '',
      toolCalls: [],
      blocks: [],
      streaming: true,
    })
    s.turnOpen = true
    s.insideThink = false
  }

  /**
   * Append raw model text, unwrapping any `<think>` block it contains.
   *
   * Tracks in-think state per task so that multiple tasks streaming concurrently
   * never corrupt each other's think boundaries.
   */
  function appendText(session: TaskSessionState, message: ChatMessage, chunk: string): void {
    let rest = chunk

    while (rest.length > 0) {
      if (session.insideThink) {
        const close = rest.indexOf(THINK_CLOSE)
        if (close === -1) {
          message.thinking += rest
          appendThinkingBlock(message, rest)
          return
        }
        const thinkChunk = rest.slice(0, close)
        message.thinking += thinkChunk
        appendThinkingBlock(message, thinkChunk)
        session.insideThink = false
        rest = rest.slice(close + THINK_CLOSE.length)
      } else {
        const open = rest.indexOf(THINK_OPEN)
        if (open === -1) {
          message.text += rest
          appendTextBlock(message, rest)
          return
        }
        const textChunk = rest.slice(0, open)
        message.text += textChunk
        appendTextBlock(message, textChunk)
        session.insideThink = true
        rest = rest.slice(open + THINK_OPEN.length)
      }
    }
  }

  function applyFrame(parsed: ParsedFrame, taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    const s = ensureSession(targetTaskId)

    const last = s.messages[s.messages.length - 1]
    const assistant = last && last.role === 'assistant' && last.streaming ? last : null

    switch (parsed.event) {
      case 'thinking_delta': {
        if (!assistant) return
        const delta = String(parsed.data.text ?? '')
        assistant.thinking += delta
        appendThinkingBlock(assistant, delta)
        return
      }

      case 'text_delta': {
        if (!assistant) return
        appendText(s, assistant, String(parsed.data.text ?? ''))
        return
      }

      case 'tool_call_start': {
        if (!assistant) return
        const record: ToolCallRecord = {
          callId: String(parsed.data.call_id ?? ''),
          tool: String(parsed.data.tool ?? ''),
          args: (parsed.data.args as Record<string, unknown>) ?? {},
          status: 'running',
          summary: '',
        }
        assistant.toolCalls.push(record)
        if (!assistant.blocks) assistant.blocks = []
        assistant.blocks.push({ type: 'tool_call', call: record })
        return
      }

      case 'tool_call_end': {
        if (!assistant) return
        const callId = String(parsed.data.call_id ?? '')
        const record = assistant.toolCalls.find((call) => call.callId === callId)
        if (record) {
          record.status = parsed.data.status === 'error' ? 'error' : 'success'
          record.summary = String(parsed.data.result_summary ?? '')
        }
        return
      }

      case 'artifact_created': {
        const filePath = String(parsed.data.file_path ?? '')
        // A task may regenerate the same file; the pane shows one entry.
        if (s.artifacts.some((item) => item.filePath === filePath)) return
        s.artifacts.push({
          type: (parsed.data.type as Artifact['type']) ?? 'text',
          filePath,
          url: String(parsed.data.url ?? ''),
        })
        return
      }

      case 'require_confirm': {
        s.pendingConfirm = {
          replyId: String(parsed.data.reply_id ?? ''),
          command: String(parsed.data.command ?? ''),
          reason: String(parsed.data.reason ?? ''),
        }
        return
      }

      case 'system_reminder': {
        if (!assistant) return
        if (!assistant.systemReminders) {
          assistant.systemReminders = []
        }
        assistant.systemReminders.push({
          blockId: String(parsed.data.block_id ?? ''),
          source: String(parsed.data.source ?? 'system'),
          content: String(parsed.data.content ?? ''),
        })
        return
      }

      case 'done': {
        if (assistant) assistant.streaming = false
        s.turnOpen = false
        return
      }

      default:
        return
    }
  }

  function resolveConfirm(_action: 'allow' | 'deny', taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    const s = ensureSession(targetTaskId)
    s.pendingConfirm = null
  }

  function reset(taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    taskSessions.value[targetTaskId] = createInitialSession()
  }

  async function loadArtifacts(taskId: string): Promise<void> {
    const s = ensureSession(taskId)
    try {
      const response = await apiClient.get<{
        artifacts: Array<{
          type: Artifact['type']
          file_path: string
          url: string
        }>
      }>(`/api/tasks/${taskId}/artifacts`)
      if (response && Array.isArray(response.artifacts)) {
        s.artifacts = response.artifacts.map((item) => ({
          type: item.type,
          filePath: item.file_path,
          url: item.url,
        }))
      }
    } catch {
      s.artifacts = []
    }
  }

  /**
   * Hydrate the middle pane from the backend transcript for a task.
   */
  async function loadHistory(taskId: string): Promise<void> {
    currentTaskId.value = taskId
    const s = ensureSession(taskId)
    s.pendingConfirm = null
    s.insideThink = false

    // If turn is open and messages exist, keep streaming view
    if (s.turnOpen && s.messages.length > 0) {
      return
    }
    try {
      const [msgResponse] = await Promise.all([
        apiClient.get<{ messages: ChatMessage[] }>(
          `/api/tasks/${taskId}/messages`,
        ),
        loadArtifacts(taskId),
      ])
      if (!s.turnOpen) {
        s.messages = msgResponse.messages ?? []
      }
    } catch {
      if (!s.turnOpen) {
        s.messages = []
      }
    }
  }

  return {
    messages,
    artifacts,
    pendingConfirm,
    isStreaming,
    currentAssistant,
    switchToTask,
    hasMessages,
    isTaskStreaming,
    addUserMessage,
    beginAssistantTurn,
    applyFrame,
    resolveConfirm,
    reset,
    loadHistory,
    loadArtifacts,
  }
})