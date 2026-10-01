<template>
  <StandaloneArtifactViewer
    v-if="isStandaloneView"
    :task-id="standaloneTaskId"
    :file-path="standaloneFilePath"
    :type="standaloneType"
  />
  <div v-else class="app-shell">
    <McHeader class="top-bar" title="MateChat">
      <template #operationArea>
        <span v-if="workspace.activeTask" class="active-task">
          {{ workspace.activeTask.title }}
        </span>
      </template>
    </McHeader>

    <main class="app-body">
      <ThreeColumnLayout />
    </main>

    <SettingsDrawer />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { McHeader } from '@matechat/core'
import ThreeColumnLayout from '@/components/layout/ThreeColumnLayout.vue'
import SettingsDrawer from '@/components/sidebar/SettingsDrawer.vue'
import StandaloneArtifactViewer from '@/components/artifacts/StandaloneArtifactViewer.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'
import { useTodosStore } from '@/store/todos'
import { useChat } from '@/composables/useChat'

const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams()
const isStandaloneView = ref(urlParams.get('view') === 'artifact')
const standaloneTaskId = ref(urlParams.get('taskId') || '')
const standaloneFilePath = ref(urlParams.get('filePath') || '')
const standaloneType = ref(urlParams.get('type') || 'markdown')

const workspace = useWorkspaceStore()
const session = useSessionStore()
const todos = useTodosStore()
const chat = useChat()

// Populate the sidebar from the backend once on load and restore active task if persisted.
// If the backend is unreachable, the sidebar just stays empty rather than blocking the UI.
onMounted(async () => {
  if (!isStandaloneView.value) {
    try {
      await workspace.fetchWorkspaces()
      const targetTaskId = workspace.activeTaskId
      if (targetTaskId && workspace.findTask(targetTaskId)) {
        session.switchToTask(targetTaskId)
        todos.switchToTask(targetTaskId)
        await Promise.all([
          session.loadHistory(targetTaskId),
          todos.loadTodos(targetTaskId),
        ])
        const task = workspace.findTask(targetTaskId)
        if (task?.status === 'running' && !chat.isTaskActive(targetTaskId)) {
          chat.reconnect(targetTaskId)
        }
      } else if (targetTaskId) {
        workspace.selectTask(null)
      }
    } catch {}
  }
})
</script>

<style scoped>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/*
 * McHeader's own root already sets `display:flex; justify-content:
 * space-between; align-items:center` (title left, #operationArea right)
 * — this just fits it into our compact 48px bar instead of the default
 * marketing-page-sized header.
 */
.top-bar {
  height: var(--topbar-height);
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
  background: #fff;
  flex-shrink: 0;
}

.top-bar :deep(.mc-header-title) {
  font-size: 14px;
  font-weight: 600;
}

.active-task {
  font-size: 12px;
  color: var(--color-text-muted);
}

.app-body {
  flex: 1;
  min-height: 0;
}
</style>