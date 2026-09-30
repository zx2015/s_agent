<template>
  <div class="workspace-tree">
    <section
      v-for="workspace in store.filteredWorkspaces"
      :key="workspace.id"
      class="workspace-group"
    >
      <header class="group-header" @click="toggle(workspace.id)">
        <span class="chevron">{{ isCollapsed(workspace.id) ? '▸' : '▾' }}</span>
        <span class="group-name">{{ workspace.name }}</span>
        <span class="group-count">{{ workspace.tasks.length }}</span>
        <button
          class="add-task-button"
          :data-test="`new-task-in-${workspace.id}`"
          title="在此工作区新建任务"
          @click.stop="onNewTaskClick(workspace.id)"
        >
          <span class="icon-add" />
        </button>
        <button
          v-if="workspace.id !== 'default'"
          class="delete-workspace-button"
          :data-test="`delete-workspace-${workspace.id}`"
          title="删除工作区"
          @click.stop="onDeleteWorkspaceClick(workspace.id, workspace.name, workspace.tasks.length)"
        >
          <McDeleteIcon :width="13" :height="13" />
        </button>
      </header>

      <McList
        v-show="!isCollapsed(workspace.id)"
        class="task-list"
        :variant="ListVariant.Transparent"
        :data="toListItems(workspace.tasks)"
        @select="onSelectTask"
      >
        <template #item="{ item }">
          <div
            class="task-item"
            :class="[`status-${item.status}`, { active: item.active }]"
            :data-test="`task-${item.value}`"
          >
            <span class="status-dot" :title="item.status" />
            <span class="task-title">{{ item.label }}</span>
            <span
              v-if="item.hasArtifacts"
              class="artifact-badge"
              :data-test="`artifact-badge-${item.value}`"
              title="有产物"
              >◈</span
            >
            <button
              class="delete-button"
              :data-test="`delete-task-${item.value}`"
              title="删除对话"
              @click.stop="onDeleteClick(String(item.value), item.label)"
            >
              <McDeleteIcon :width="14" :height="14" />
            </button>
          </div>
        </template>
      </McList>
    </section>

    <p v-if="store.filteredWorkspaces.length === 0" class="empty">
      没有匹配的任务
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { McList } from '@matechat/core'
import { McDeleteIcon } from '@matechat/core/Toolbar'
import { ListVariant } from '@matechat/core/List'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'
import type { Task } from '@/types'

const store = useWorkspaceStore()
const session = useSessionStore()
const collapsed = ref<Set<string>>(new Set())

/** McList's ListItemData, extended with the task fields the `#item` slot needs. */
interface TaskListItem {
  label: string
  value: string
  active: boolean
  status: Task['status']
  hasArtifacts: boolean
}

function toListItems(tasks: Task[]): TaskListItem[] {
  return tasks.map((task) => ({
    label: task.title,
    value: task.id,
    active: task.id === store.activeTaskId,
    status: task.status,
    hasArtifacts: task.hasArtifacts,
  }))
}

function isCollapsed(workspaceId: string): boolean {
  return collapsed.value.has(workspaceId)
}

function toggle(workspaceId: string): void {
  const next = new Set(collapsed.value)
  if (next.has(workspaceId)) {
    next.delete(workspaceId)
  } else {
    next.add(workspaceId)
  }
  collapsed.value = next
}

/**
 * Targets a task at a specific workspace — the direct answer to "how do
 * I pick which workspace a new task goes into": click "+" on that
 * workspace's own row, rather than always landing in whichever workspace
 * happens to be first (see `SidebarLeft.vue`'s top-level "+ 新建任务",
 * which still does that for a quick default). `@click.stop` keeps this
 * from also toggling the group's collapse state.
 */
async function onSelectTask(item: { value: string | number }): Promise<void> {
  const taskId = String(item.value)
  if (store.activeTaskId === taskId) return
  store.selectTask(taskId)
  // Hydrate the middle pane with this task's persisted conversation history
  // from the backend. Without this, the bubbles from the previously active
  // task would linger on screen while the backend runs against the new task's
  // context — a major visual disconnect.
  await session.loadHistory(taskId)
}

/**
 * Targets a task at a specific workspace — the direct answer to "how do
 * I pick which workspace a new task goes into": click "+" on that
 * workspace's own row, rather than always landing in whichever workspace
 * happens to be first (see `SidebarLeft.vue`'s top-level "+ 新建任务",
 * which still does that for a quick default). `@click.stop` keeps this
 * from also toggling the group's collapse state.
 */
async function onNewTaskClick(workspaceId: string): Promise<void> {
  const task = await store.createTaskRemote(workspaceId, '新任务')
  store.selectTask(task.id)
  session.reset()
}

/**
 * Delete is permanent (backend removes the task's metadata, persisted
 * conversation history, and workspace files — see
 * `TaskManager.delete_task`), so it's gated behind a confirm dialog
 * rather than firing straight from the click. `@click.stop` on the
 * button keeps this from also selecting the row via McList's own click
 * handling.
 */
async function onDeleteClick(taskId: string, title: string): Promise<void> {
  if (!window.confirm(`确定要删除对话"${title}"吗？此操作不可撤销。`)) return

  const wasActive = store.activeTaskId === taskId
  await store.deleteTaskRemote(taskId)
  if (wasActive) {
    session.reset()
  }
}

/**
 * Deleting a workspace cascades to every task inside it on the backend
 * (`TaskManager.delete_workspace`, mirroring deleting a folder on a real
 * filesystem) — the confirm message spells out the task count up front
 * so this doesn't read as "delete an empty folder" when it's actually
 * about to take N conversations with it.
 */
async function onDeleteWorkspaceClick(
  workspaceId: string,
  name: string,
  taskCount: number,
): Promise<void> {
  const message =
    taskCount > 0
      ? `确定要删除工作区"${name}"吗？里面的 ${taskCount} 个对话会一起被删除，此操作不可撤销。`
      : `确定要删除工作区"${name}"吗？此操作不可撤销。`
  if (!window.confirm(message)) return

  const hadActiveTask = store.workspaces
    .find((ws) => ws.id === workspaceId)
    ?.tasks.some((task) => task.id === store.activeTaskId)
  await store.deleteWorkspaceRemote(workspaceId)
  if (hadActiveTask) session.reset()
}
</script>

<style scoped>
.workspace-tree {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  flex: 1;
  padding: 4px 0;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.group-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
}

.add-task-button {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 12px;
}

.group-header:hover .add-task-button {
  display: flex;
}

.add-task-button:hover {
  background: var(--color-bg-subtle);
  color: #165dff;
}

.delete-workspace-button {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
}

.group-header:hover .delete-workspace-button {
  display: flex;
}

.delete-workspace-button:hover {
  background: #ffece8;
  color: #f53f3f;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px 7px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.task-item:hover {
  background: var(--color-bg-subtle);
}

.task-item.active {
  background: #e8f3ff;
  color: #165dff;
}

.task-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-button {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
}

.task-item:hover .delete-button {
  display: flex;
}

.delete-button:hover {
  background: #ffece8;
  color: #f53f3f;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c9cdd4;
  flex-shrink: 0;
}

.status-running .status-dot {
  background: #165dff;
}

.status-completed .status-dot {
  background: #00b42a;
}

.status-failed .status-dot {
  background: #f53f3f;
}

.status-suspended .status-dot {
  background: #ff7d00;
}

.artifact-badge {
  font-size: 11px;
  color: var(--color-text-muted);
}

.empty {
  font-size: 12px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 16px 0;
}
</style>
