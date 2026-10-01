/**
 * The Pinia store holding the active task's todo list.
 *
 * Source of truth is AgentScope's `AgentState.tasks_context.tasks` on the
 * backend. The frontend never creates or edits these directly — they are
 * populated via:
 *
 * 1. Cold fetch on task switch: `GET /api/tasks/{task_id}/todos`
 * 2. Real-time updates during a turn: `task_todos_changed` SSE frames
 *
 * The store maintains a per-task cache so that switching tasks does not
 * discard active todos, and background tasks can update their own todos
 * without stomping on the currently focused task.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient } from '@/api/client'
import { useWorkspaceStore } from '@/store/workspaces'
import type { TodoItem } from '@/types'

const DEFAULT_TASK_ID = '__default__'

export const useTodosStore = defineStore('todos', () => {
  const workspace = useWorkspaceStore()
  const currentTaskId = ref<string>(DEFAULT_TASK_ID)
  const taskTodos = ref<Record<string, TodoItem[]>>({
    [DEFAULT_TASK_ID]: [],
  })

  function resolveTaskId(targetTaskId?: string): string {
    return targetTaskId || workspace.activeTaskId || currentTaskId.value || DEFAULT_TASK_ID
  }

  const todos = computed<TodoItem[]>({
    get: () => {
      const id = resolveTaskId()
      return taskTodos.value[id] ?? []
    },
    set: (val: TodoItem[]) => {
      const id = resolveTaskId()
      taskTodos.value[id] = val
    },
  })

  const completedCount = computed(
    () => todos.value.filter((t) => t.state === 'completed').length,
  )

  const activeCount = computed(
    () =>
      todos.value.filter(
        (t) => t.state === 'in_progress' || t.state === 'pending',
      ).length,
  )

  const summary = computed(() => {
    if (todos.value.length === 0) return null
    return `${completedCount.value} / ${todos.value.length} 待办完成`
  })

  function switchToTask(taskId: string): void {
    currentTaskId.value = taskId
    if (!taskTodos.value[taskId]) {
      taskTodos.value[taskId] = []
    }
  }

  async function loadTodos(taskId: string): Promise<void> {
    currentTaskId.value = taskId
    try {
      const response = await apiClient.get<{ todos: TodoItem[] }>(
        `/api/tasks/${taskId}/todos`,
      )
      taskTodos.value[taskId] = response.todos ?? []
    } catch {
      taskTodos.value[taskId] = []
    }
  }

  function applyFrame(
    payload: { todos?: TodoItem[] } | null | undefined,
    taskId?: string,
  ): void {
    if (!payload || !Array.isArray(payload.todos)) return
    const targetTaskId = resolveTaskId(taskId)
    taskTodos.value[targetTaskId] = payload.todos
  }

  function clear(taskId?: string): void {
    const targetTaskId = resolveTaskId(taskId)
    taskTodos.value[targetTaskId] = []
  }

  return {
    todos,
    completedCount,
    activeCount,
    summary,
    switchToTask,
    loadTodos,
    applyFrame,
    clear,
  }
})