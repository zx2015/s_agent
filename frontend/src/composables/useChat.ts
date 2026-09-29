/**
 * Wiring between the chat input and the agent stream.
 *
 * Two modes share one code path:
 *
 * * **Live** — `POST /api/chat` returns an SSE stream that is consumed
 *   frame by frame.
 * * **Mock** — when `VITE_USE_MOCK` is set, the local simulator stands in.
 *   This is what lets the workbench be built and demoed without a backend.
 *
 * Switching between them is a build-time flag rather than a code change,
 * so integration testing is a one-line diff.
 */
import { ref } from 'vue'
import { apiClient } from '@/api/client'
import { parseSseFrame } from '@/api/events'
import { mockTurn } from '@/mock/sse-server'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export function useChat() {
  const session = useSessionStore()
  const workspace = useWorkspaceStore()
  const abortController = ref<AbortController | null>(null)

  /**
   * Send one message and stream the reply into the session store.
   *
   * @param message - The user's message.
   */
  async function send(message: string): Promise<void> {
    if (session.isStreaming) return

    // Record the user's turn before checking for a task, so the transcript
    // shows what was typed even if there is nowhere to run it.
    session.addUserMessage(message)

    const taskId = workspace.activeTaskId
    if (!taskId) return

    session.beginAssistantTurn()

    if (USE_MOCK) {
      const noWait = () => Promise.resolve()
      for await (const frame of mockTurn(message, noWait)) {
        const parsed = parseSseFrame(frame)
        if (parsed) session.applyFrame(parsed)
      }
      return
    }

    const controller = new AbortController()
    abortController.value = controller

    try {
      for await (const parsed of apiClient.stream('/api/chat', {
        task_id: taskId,
        message,
      })) {
        session.applyFrame(parsed as never)
      }
    } catch {
      // The stream can fail mid-flight (backend restart, network drop).
      // Surface it in the transcript rather than leaving a spinner that
      // never resolves.
      session.applyFrame({
        event: 'text_delta',
        data: { text: '\n\n[连接中断]' },
      } as never)
      session.applyFrame({
        event: 'done',
        data: { task_status: 'failed' },
      } as never)
    } finally {
      abortController.value = null
    }
  }

  /** Abort the in-flight turn. */
  function stop(): void {
    abortController.value?.abort()
    session.applyFrame({
      event: 'done',
      data: { task_status: 'aborted' },
    } as never)
  }

  return { send, stop }
}