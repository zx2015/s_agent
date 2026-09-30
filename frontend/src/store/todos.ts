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
 * The store treats every update as a complete snapshot: applying a
 * frame overwrites the entire list rather than attempting to diff.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient } from '@/api/client'
import type { TodoItem } from '@/types'

export const useTodosStore = defineStore('todos', () => {
  const todos = ref<TodoItem[]>([])

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

  async function loadTodos(taskId: string): Promise<void> {
    clear()
    try {
      const response = await apiClient.get<{ todos: TodoItem[] }>(
        `/api/tasks/${taskId}/todos`,
      )
      todos.value = response.todos ?? []
    } catch {
      todos.value = []
    }
  }

  function applyFrame(payload: { todos?: TodoItem[] } | null | undefined): void {
    if (!payload || !Array.isArray(payload.todos)) return
    todos.value = payload.todos
  }

  function clear(): void {
    todos.value = []
  }

  return {
    todos,
    completedCount,
    activeCount,
    summary,
    loadTodos,
    applyFrame,
    clear,
  }
})