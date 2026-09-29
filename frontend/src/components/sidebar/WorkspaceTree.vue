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

      <ul v-show="!isCollapsed(workspace.id)" class="task-list">
        <li
          v-for="task in workspace.tasks"
          :key="task.id"
          class="task-item"
          :class="[`status-${task.status}`, { active: task.id === store.activeTaskId }]"
          :data-test="`task-${task.id}`"
          @click="store.selectTask(task.id)"
        >
          <span class="status-dot" :title="task.status" />
          <span class="task-title">{{ task.title }}</span>
          <span
            v-if="task.hasArtifacts"
            class="artifact-badge"
            :data-test="`artifact-badge-${task.id}`"
            title="有产物"
            >◈</span
          >
        </li>
      </ul>
    </section>

    <p v-if="store.filteredWorkspaces.length === 0" class="empty">
      没有匹配的任务
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspaceStore } from '@/store/workspaces'

const store = useWorkspaceStore()
const collapsed = ref<Set<string>>(new Set())

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
  color: #86909c;
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

.task-list {
  list-style: none;
  margin: 0;
  padding: 0;
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
  color: #86909c;
}

.empty {
  font-size: 12px;
  color: #86909c;
  text-align: center;
  padding: 16px 0;
}
</style>
