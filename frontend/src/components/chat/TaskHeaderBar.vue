<template>
  <header class="task-header">
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

    <div class="actions">
      <button class="action" :disabled="!task" @click="startEditing">
        重命名
      </button>
      <button class="action" :disabled="!task" @click="archive">归档</button>
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

const store = useWorkspaceStore()
const session = useSessionStore()

const task = computed(() => store.activeTask)

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

function archive(): void {
  if (store.activeTaskId) {
    store.archiveTask(store.activeTaskId)
  }
}

function clearContext(): void {
  session.reset()
}
</script>

<style scoped>
.task-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--color-border);
  min-height: 48px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  flex: 1;
  cursor: text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  border: 1px solid #165dff;
  border-radius: 4px;
}

.actions {
  display: flex;
  gap: 4px;
}

.action {
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
}

.action:disabled {
  color: #c9cdd4;
  cursor: not-allowed;
}

.action:not(:disabled):hover {
  background: var(--color-bg-subtle);
}
</style>