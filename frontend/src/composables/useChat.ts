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
   * Make sure a task is selected before running a turn, creating one on
   * the fly if the user never picked one from the sidebar.
   *
   * Without this, sending a message with no active task silently did
   * nothing beyond echoing the user's own bubble — `send()` used to
   * return right after the `if (!taskId) return` check, before ever
   * calling the backend. Auto-creating a task here means "just type and
   * send" works the same way it would in a chat product that doesn't
   * force the user to create a project first.
   *
   * @returns The task id to run against, or `null` if creation failed
   *   (e.g. the backend is unreachable).
   */
  async function ensureActiveTask(): Promise<string | null> {
    if (workspace.activeTaskId) return workspace.activeTaskId

    const workspaceId = workspace.workspaces[0]?.id ?? 'default'

    if (USE_MOCK) {
      if (!workspace.workspaces.some((item) => item.id === workspaceId)) {
        workspace.setWorkspaces([{ id: workspaceId, name: '默认工作区', tasks: [] }])
      }
      const task = workspace.createTask(workspaceId, '新任务')
      workspace.selectTask(task.id)
      return task.id
    }

    try {
      const task = await workspace.createTaskRemote(workspaceId, '新任务')
      workspace.selectTask(task.id)
      return task.id
    } catch {
      return null
    }
  }

  /**
   * Send one message and stream the reply into the session store.
   *
   * @param message - The user's message.
   */
  async function send(message: string): Promise<void> {
    if (session.isStreaming) return

    // Record the user's turn before resolving a task, so the transcript
    // shows what was typed even if task creation ends up failing.
    session.addUserMessage(message)

    const taskId = await ensureActiveTask()

    session.beginAssistantTurn()

    if (!taskId) {
      session.applyFrame({
        event: 'text_delta',
        data: { text: '无法创建任务，请确认后端服务是否已启动。' },
      } as never)
      session.applyFrame({
        event: 'done',
        data: { task_status: 'failed' },
      } as never)
      return
    }

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

  /**
   * Resolve a pending HITL confirmation.
   *
   * Posting to `/api/tasks/{id}/confirm` resolves the `asyncio.Future`
   * the backend's still-open `/api/chat` SSE connection is awaiting (see
   * `server/service/task_manager.py`), so the same stream resumes and
   * keeps yielding frames after this call returns. The card is cleared
   * locally either way — a stale confirm request (network error, task
   * already moved on) should not leave the UI stuck.
   */
  async function confirmToolCall(action: 'allow' | 'deny'): Promise<void> {
    const pending = session.pendingConfirm
    const taskId = workspace.activeTaskId
    session.resolveConfirm(action)
    if (!pending || !taskId || USE_MOCK) return

    try {
      await apiClient.post(`/api/tasks/${taskId}/confirm`, {
        replyId: pending.replyId,
        action,
      })
    } catch {
      // Nothing more to do — the card is already cleared, and the
      // backend's own turn will time out/error on its side.
    }
  }

  return { send, stop, confirmToolCall }
}