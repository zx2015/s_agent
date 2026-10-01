/**
 * The conversation state for the middle pane.
 *
 * Two pieces of real-world handling live here rather than in components:
 *
 * 1. `<think>` unwrapping. The `v-flash` model streams its reasoning
 *    wrapped in `<think>…</think>` inside the text channel (verified
 *    against the live model on 2026-09-28). Leaving those tags in the
 *    transcript would show raw markup to the user.
 * 2. Turn guarding. Frames are ignored unless a turn is open, so a straggler
 *    arriving after a reset cannot repopulate a cleared conversation.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient } from '@/api/client'
import type { ParsedFrame } from '@/api/events'
import type { Artifact, ChatMessage, PendingConfirm } from '@/types'

let messageCounter = 0

function newMessageId(): string {
  messageCounter += 1
  return `msg-${Date.now()}-${messageCounter}`
}

const THINK_OPEN = '<think>'
const THINK_CLOSE = '</think>'

export const useSessionStore = defineStore('session', () => {
  const messages = ref<ChatMessage[]>([])
  const artifacts = ref<Artifact[]>([])
  const pendingConfirm = ref<PendingConfirm | null>(null)
  const turnOpen = ref(false)

  /**
   * Per-message think-stripping state. Stored outside the message itself
   * so resetting the array (which loses the message) automatically loses
   * the flag — preventing one turn's in-progress think from bleeding into
   * the next.
   */
  const insideThink = ref(false)

  /** The assistant message currently being streamed, if any. */
  const currentAssistant = computed<ChatMessage | null>(() => {
    const last = messages.value[messages.value.length - 1]
    return last && last.role === 'assistant' && last.streaming ? last : null
  })

  const isStreaming = computed(() => turnOpen.value)

  function addUserMessage(text: string): void {
    messages.value.push({
      id: newMessageId(),
      role: 'user',
      text,
      thinking: '',
      toolCalls: [],
      streaming: false,
    })
  }

  function beginAssistantTurn(): void {
    messages.value.push({
      id: newMessageId(),
      role: 'assistant',
      text: '',
      thinking: '',
      toolCalls: [],
      streaming: true,
    })
    turnOpen.value = true
    insideThink.value = false
  }

  /**
   * Append raw model text, unwrapping any `<think>` block it contains.
   *
   * Tracks in-think state via the module-level flag so a `<think>` opened
   * at the end of one chunk closes cleanly when the closing tag arrives
   * in the next — the tag must never leak into the visible answer.
   *
   * @param message - The assistant message to append to.
   * @param chunk - The raw chunk, which may contain thinking tags.
   */
  function appendText(message: ChatMessage, chunk: string): void {
    let rest = chunk

    while (rest.length > 0) {
      if (insideThink.value) {
        const close = rest.indexOf(THINK_CLOSE)
        if (close === -1) {
          message.thinking += rest
          return
        }
        message.thinking += rest.slice(0, close)
        insideThink.value = false
        rest = rest.slice(close + THINK_CLOSE.length)
      } else {
        const open = rest.indexOf(THINK_OPEN)
        if (open === -1) {
          message.text += rest
          return
        }
        message.text += rest.slice(0, open)
        insideThink.value = true
        rest = rest.slice(open + THINK_OPEN.length)
      }
    }
  }

  function applyFrame(parsed: ParsedFrame): void {
    switch (parsed.event) {
      case 'thinking_delta': {
        const message = currentAssistant.value
        if (!message) return
        message.thinking += String(parsed.data.text ?? '')
        return
      }

      case 'text_delta': {
        const message = currentAssistant.value
        if (!message) return
        appendText(message, String(parsed.data.text ?? ''))
        return
      }

      case 'tool_call_start': {
        const message = currentAssistant.value
        if (!message) return
        message.toolCalls.push({
          callId: String(parsed.data.call_id ?? ''),
          tool: String(parsed.data.tool ?? ''),
          args: (parsed.data.args as Record<string, unknown>) ?? {},
          status: 'running',
          summary: '',
        })
        return
      }

      case 'tool_call_end': {
        const message = currentAssistant.value
        if (!message) return
        const callId = String(parsed.data.call_id ?? '')
        const record = message.toolCalls.find((call) => call.callId === callId)
        if (record) {
          record.status = parsed.data.status === 'error' ? 'error' : 'success'
          record.summary = String(parsed.data.result_summary ?? '')
        }
        return
      }

      case 'artifact_created': {
        const filePath = String(parsed.data.file_path ?? '')
        // A task may regenerate the same file; the pane shows one entry.
        if (artifacts.value.some((item) => item.filePath === filePath)) return
        artifacts.value.push({
          type: (parsed.data.type as Artifact['type']) ?? 'text',
          filePath,
          url: String(parsed.data.url ?? ''),
        })
        return
      }

      case 'require_confirm': {
        pendingConfirm.value = {
          replyId: String(parsed.data.reply_id ?? ''),
          command: String(parsed.data.command ?? ''),
          reason: String(parsed.data.reason ?? ''),
        }
        return
      }

      case 'system_reminder': {
        const message = currentAssistant.value
        if (!message) return
        if (!message.systemReminders) {
          message.systemReminders = []
        }
        message.systemReminders.push({
          blockId: String(parsed.data.block_id ?? ''),
          source: String(parsed.data.source ?? 'system'),
          content: String(parsed.data.content ?? ''),
        })
        return
      }

      case 'done': {
        const message = currentAssistant.value
        if (message) message.streaming = false
        turnOpen.value = false
        return
      }

      default:
        return
    }
  }

  function resolveConfirm(_action: 'allow' | 'deny'): void {
    pendingConfirm.value = null
  }

  function reset(): void {
    messages.value = []
    artifacts.value = []
    pendingConfirm.value = null
    turnOpen.value = false
    insideThink.value = false
  }

  /**
   * Hydrate the middle pane from the backend transcript for a task.
   *
   * Called by the sidebar when the user switches tasks. Without this,
   * clicking from task A to task B would leave A's bubbles on screen
   * while the next user message lands on B's model context — a clear
   * disconnect between what the user sees and what the agent sees.
   */
  async function loadHistory(taskId: string): Promise<void> {
    reset()
    try {
      const response = await apiClient.get<{ messages: ChatMessage[] }>(
        `/api/tasks/${taskId}/messages`,
      )
      messages.value = response.messages ?? []
    } catch {
      // A failed hydrate must not break the session: start clean.
      messages.value = []
    }
  }

  return {
    messages,
    artifacts,
    pendingConfirm,
    isStreaming,
    currentAssistant,
    addUserMessage,
    beginAssistantTurn,
    applyFrame,
    resolveConfirm,
    reset,
    loadHistory,
  }
})