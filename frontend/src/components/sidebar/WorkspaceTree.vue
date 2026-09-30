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
      </header>

      <McList
        v-show="!isCollapsed(workspace.id)"
        class="task-list"
        :variant="ListVariant.Transparent"
        :data="toListItems(workspace.tasks)"
        @select="(item) => store.selectTask(String(item.value))"
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
              ✕
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
  if (wasActive) session.reset()
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
