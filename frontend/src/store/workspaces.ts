/**
 * Workspace and task state for the left sidebar.
 *
 * Two invariants drive the design:
 *
 * 1. Search filters the *tree*, not a flat list — a workspace with no
 *    matching tasks disappears rather than rendering an empty group.
 * 2. Archiving the active task clears the selection. Leaving it set would
 *    strand the chat pane on a task the sidebar no longer shows.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient } from '@/api/client'
import type { Task, Workspace } from '@/types'

let taskCounter = 0

function newTaskId(): string {
  taskCounter += 1
  return `task-${Date.now()}-${taskCounter}`
}

export const useWorkspaceStore = defineStore('workspaces', () => {
  const workspaces = ref<Workspace[]>([])
  const searchQuery = ref('')
  const activeTaskId = ref<string | null>(null)

  /** Workspaces with their task lists filtered by the current query. */
  const filteredWorkspaces = computed<Workspace[]>(() => {
    const query = searchQuery.value.trim().toLowerCase()
    if (!query) return workspaces.value

    return workspaces.value
      .map((workspace) => ({
        ...workspace,
        tasks: workspace.tasks.filter((task) =>
          task.title.toLowerCase().includes(query),
        ),
      }))
      .filter((workspace) => workspace.tasks.length > 0)
  })

  const activeTask = computed<Task | null>(
    () => findTask(activeTaskId.value) ?? null,
  )

  function setWorkspaces(next: Workspace[]): void {
    workspaces.value = next
  }

  function setSearchQuery(query: string): void {
    searchQuery.value = query
  }

  function findTask(taskId: string | null): Task | undefined {
    if (!taskId) return undefined
    for (const workspace of workspaces.value) {
      const found = workspace.tasks.find((task) => task.id === taskId)
      if (found) return found
    }
    return undefined
  }

  function selectTask(taskId: string): void {
    activeTaskId.value = taskId
  }

  function renameTask(taskId: string, title: string): void {
    const trimmed = title.trim()
    if (!trimmed) return
    const task = findTask(taskId)
    if (task) {
      task.title = trimmed
      task.updatedAt = new Date().toISOString()
    }
  }

  function archiveTask(taskId: string): void {
    for (const workspace of workspaces.value) {
      const index = workspace.tasks.findIndex((task) => task.id === taskId)
      if (index >= 0) {
        workspace.tasks.splice(index, 1)
        break
      }
    }
    // Keep the selection consistent with the visible tree.
    if (activeTaskId.value === taskId) {
      activeTaskId.value = null
    }
  }

  function createTask(workspaceId: string, title: string): Task {
    const workspace = workspaces.value.find((item) => item.id === workspaceId)
    if (!workspace) {
      throw new Error(`Unknown workspace ${workspaceId}`)
    }

    const task: Task = {
      id: newTaskId(),
      title,
      workspaceId,
      status: 'running',
      updatedAt: new Date().toISOString(),
      hasArtifacts: false,
    }
    workspace.tasks.unshift(task)
    return task
  }

  function markArtifacts(taskId: string): void {
    const task = findTask(taskId)
    if (task) task.hasArtifacts = true
  }

  /**
   * Load the workspace/task tree from the backend.
   *
   * Called once on app start (see `App.vue`). The backend always returns
   * at least a `default` workspace (see `server/service/task_manager.py`),
   * so `createTaskRemote` below never has to special-case "no workspace
   * exists yet".
   */
  async function fetchWorkspaces(): Promise<void> {
    const response = await apiClient.get<{ workspaces: Workspace[] }>(
      '/api/workspaces',
    )
    setWorkspaces(response.workspaces)
  }

  /**
   * Create a task via the backend (so its workspace directory and git
   * repo exist before the first chat message) and reflect it locally.
   */
  async function createTaskRemote(
    workspaceId: string,
    title: string,
  ): Promise<Task> {
    const task = await apiClient.post<Task>('/api/tasks', {
      workspaceId,
      title,
    })
    let workspace = workspaces.value.find((item) => item.id === workspaceId)
    if (!workspace) {
      workspace = { id: workspaceId, name: workspaceId, tasks: [] }
      workspaces.value.push(workspace)
    }
    workspace.tasks.unshift(task)
    return task
  }

  return {
    workspaces,
    searchQuery,
    activeTaskId,
    filteredWorkspaces,
    activeTask,
    setWorkspaces,
    setSearchQuery,
    findTask,
    selectTask,
    renameTask,
    archiveTask,
    createTask,
    markArtifacts,
    fetchWorkspaces,
    createTaskRemote,
  }
})