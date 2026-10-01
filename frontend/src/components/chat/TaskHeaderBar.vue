<template>
  <header class="task-header">
    <div class="task-info">
      <input
        v-if="editing"
        ref="titleInput"
        v-model="draftTitle"
        class="title-input"
        @blur="commit"
        @keydown.enter="commit"
        @keydown.esc="cancel"
      />
      <h2 v-else class="title" @click="startEditing">
        {{ task?.title ?? '未选择任务' }}
      </h2>

      <div v-if="task" class="workspace-tags">
        <span class="workspace-badge" :title="`所属工作区: ${currentWorkspaceName}`">
          📁 {{ currentWorkspaceName }}
        </span>
        <span
          v-if="task.workspacePath"
          class="path-badge"
          :title="`工作区物理路径: ${task.workspacePath}`"
        >
          {{ task.workspacePath }}
        </span>
      </div>
    </div>

    <div class="actions">
      <button
        v-if="session.isStreaming"
        class="action action-danger"
        title="立即强制中断生成"
        @click="stop()"
      >
        ⏹ 强制中断
      </button>

      <button class="action" :disabled="!task" @click="startEditing">
        重命名
      </button>
      <button class="action" :disabled="!task" @click="archive">
        归档
      </button>
      <button class="action" :disabled="!task" @click="clearContext">
        清空上下文
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const store = useWorkspaceStore()
const session = useSessionStore()
const { stop } = useChat()

const task = computed(() => store.activeTask)

const currentWorkspaceName = computed(() => {
  if (!task.value?.workspaceId) return '默认工作区'
  const ws = store.workspaces.find((w) => w.id === task.value?.workspaceId)
  return ws?.name ?? '默认工作区'
})

const editing = ref(false)
const draftTitle = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

async function startEditing(): Promise<void> {
  if (!store.activeTask) return
  draftTitle.value = store.activeTask.title
  editing.value = true
  await nextTick()
  titleInput.value?.focus()
}

function commit(): void {
  if (store.activeTaskId) {
    store.renameTask(store.activeTaskId, draftTitle.value)
  }
  editing.value = false
}

function cancel(): void {
  editing.value = false
}

async function archive(): Promise<void> {
  if (store.activeTaskId) {
    try {
      await store.archiveTaskRemote(store.activeTaskId)
    } catch (err) {
      console.error('Failed to archive task on backend:', err)
      store.archiveTask(store.activeTaskId)
    }
  }
}

async function clearContext(): Promise<void> {
  if (store.activeTaskId) {
    try {
      await store.resetTaskContextRemote(store.activeTaskId)
    } catch (err) {
      console.error('Failed to reset task context on backend:', err)
    }
  }
  session.reset()
}
</script>

<style scoped>
.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--color-border);
  min-height: 48px;
  background: var(--color-bg-base, #fff);
}

.task-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  cursor: text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  border: 1px solid #165dff;
  border-radius: 4px;
  background: var(--color-bg-base, #fff);
  color: var(--color-text);
}

.workspace-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.workspace-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-bg-subtle, #f2f3f5);
  color: var(--color-text-secondary, #4e5969);
  border: 1px solid var(--color-border);
  white-space: nowrap;
}

.path-badge {
  font-size: 11px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-bg-subtle, #f2f3f5);
  color: var(--color-text-muted, #86909c);
  border: 1px solid var(--color-border);
  font-family: monospace;
}

.actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.action {
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg-base, #fff);
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action:disabled {
  color: #c9cdd4;
  cursor: not-allowed;
}

.action:not(:disabled):hover {
  background: var(--color-bg-subtle);
}

.action-danger {
  color: #f53f3f;
  border-color: #f53f3f;
  background: #fff;
  font-weight: 500;
}

.action-danger:hover {
  background: #ffece8 !important;
}
</style>