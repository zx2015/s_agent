/**
 * Wiring between the chat input and the agent stream.
 *
 * Supports multi-session concurrent execution:
 * - Each running task has its own AbortController and stream consumer loop.
 * - Switching away from a task keeps the task executing in the background.
 * - Switching back to a task or refreshing connects seamlessly via /events.
 * - Stopping a task triggers backend abort and cancels local stream.
 */
import { apiClient, ApiError } from '@/api/client'
import { parseSseFrame } from '@/api/events'
import { mockTurn } from '@/mock/sse-server'
import { useSessionStore } from '@/store/session'
import { useSettingsStore } from '@/store/settings'
import { useTodosStore } from '@/store/todos'
import { useWorkspaceStore } from '@/store/workspaces'
import type { Task } from '@/types'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const activeControllers = new Map<string, AbortController>()

export function useChat() {
  const session = useSessionStore()
  const workspace = useWorkspaceStore()
  const todos = useTodosStore()
  const settings = useSettingsStore()

  /**
   * Make sure a task is selected before running a turn, creating one on
   * the fly if the user never picked one from the sidebar.
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
      session.switchToTask(task.id)
      todos.switchToTask(task.id)
      return task.id
    }

    try {
      const task = await workspace.createTaskRemote(workspaceId, '新任务')
      workspace.selectTask(task.id)
      session.switchToTask(task.id)
      todos.switchToTask(task.id)
      return task.id
    } catch {
      return null
    }
  }

  function isTaskActive(taskId: string): boolean {
    return activeControllers.has(taskId)
  }

  /**
   * Send one message and stream the reply into the session store.
   * Runs independently per task so switching away does not abort.
   */
  async function send(message: string): Promise<void> {
    const taskId = await ensureActiveTask()

    if (!taskId) {
      session.addUserMessage(message)
      session.beginAssistantTurn()
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

    if (session.isTaskStreaming(taskId)) return

    session.addUserMessage(message, taskId)
    session.beginAssistantTurn(taskId)
    workspace.updateTaskStatus(taskId, 'running')

    if (USE_MOCK) {
      const noWait = () => Promise.resolve()
      for await (const frame of mockTurn(message, noWait)) {
        const parsed = parseSseFrame(frame)
        if (parsed?.event === 'task_todos_changed') {
          todos.applyFrame(parsed.data as never, taskId)
        } else if (parsed) {
          session.applyFrame(parsed, taskId)
        }
      }
      workspace.updateTaskStatus(taskId, 'completed')
      return
    }

    const controller = new AbortController()
    activeControllers.set(taskId, controller)

    try {
      for await (const parsed of apiClient.stream(
        '/api/chat',
        {
          task_id: taskId,
          message,
          model_name: settings.modelName,
          base_url: settings.baseUrl,
          hitl_mode: settings.hitlMode,
        },
        controller.signal,
      )) {
        if (parsed.event === 'task_renamed') {
          workspace.renameTask(taskId, String(parsed.data.title))
          continue
        }
        if (parsed.event === 'task_todos_changed') {
          todos.applyFrame(parsed.data as never, taskId)
          continue
        }
        if (parsed.event === 'artifact_created') {
          workspace.markArtifacts(taskId)
        }
        if (parsed.event === 'done') {
          const status = String(parsed.data.task_status || 'completed') as Task['status']
          workspace.updateTaskStatus(taskId, status)
        }
        session.applyFrame(parsed as never, taskId)
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        session.applyFrame({
          event: 'done',
          data: { task_status: 'aborted' },
        } as never, taskId)
        workspace.updateTaskStatus(taskId, 'completed')
        return
      }

      const errorText =
        err instanceof ApiError && err.status === 409
          ? '\n\n[任务正在处理上一条消息，请稍后再试]'
          : '\n\n[连接中断]'
      session.applyFrame({
        event: 'text_delta',
        data: { text: errorText },
      } as never, taskId)
      session.applyFrame({
        event: 'done',
        data: { task_status: 'failed' },
      } as never, taskId)
      workspace.updateTaskStatus(taskId, 'failed')
    } finally {
      activeControllers.delete(taskId)
    }
  }

  /**
   * Reconnect to an in-flight background task to resume stream updates.
   */
  async function reconnect(taskId: string): Promise<void> {
    if (activeControllers.has(taskId) || USE_MOCK) return

    const controller = new AbortController()
    activeControllers.set(taskId, controller)

    if (!session.isTaskStreaming(taskId)) {
      session.beginAssistantTurn(taskId)
    }

    try {
      for await (const parsed of apiClient.streamGet(
        `/api/tasks/${taskId}/events`,
        controller.signal,
      )) {
        if (parsed.event === 'task_renamed') {
          workspace.renameTask(taskId, String(parsed.data.title))
          continue
        }
        if (parsed.event === 'task_todos_changed') {
          todos.applyFrame(parsed.data as never, taskId)
          continue
        }
        if (parsed.event === 'artifact_created') {
          workspace.markArtifacts(taskId)
        }
        if (parsed.event === 'done') {
          const status = String(parsed.data.task_status || 'completed') as Task['status']
          workspace.updateTaskStatus(taskId, status)
        }
        session.applyFrame(parsed as never, taskId)
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        session.applyFrame({
          event: 'done',
          data: { task_status: 'aborted' },
        } as never, taskId)
        workspace.updateTaskStatus(taskId, 'completed')
        return
      }
    } finally {
      activeControllers.delete(taskId)
    }
  }

  /** Abort the in-flight turn for the current or specified task. */
  async function stop(targetTaskId?: string): Promise<void> {
    const taskId = targetTaskId || workspace.activeTaskId || '__default__'

    const controller = activeControllers.get(taskId)
    controller?.abort()
    activeControllers.delete(taskId)

    if (!USE_MOCK && taskId !== '__default__') {
      try {
        await apiClient.post(`/api/tasks/${taskId}/abort`, {})
      } catch {
        // Backend abort is best effort
      }
    }

    session.applyFrame({
      event: 'done',
      data: { task_status: 'aborted' },
    } as never, taskId)
    workspace.updateTaskStatus(taskId, 'completed')
  }

  /**
   * Resolve a pending HITL confirmation.
   */
  async function confirmToolCall(action: 'allow' | 'deny', targetTaskId?: string): Promise<void> {
    const taskId = targetTaskId || workspace.activeTaskId
    if (!taskId) return

    const pending = session.pendingConfirm
    session.resolveConfirm(action, taskId)
    if (!pending || USE_MOCK) return

    try {
      await apiClient.post(`/api/tasks/${taskId}/confirm`, {
        replyId: pending.replyId,
        action,
      })
    } catch {
      // Best-effort
    }
  }

  return { send, stop, reconnect, isTaskActive, confirmToolCall }
}