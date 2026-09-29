<template>
  <aside class="sidebar-right">
    <ArtifactTabs v-model:active-tab="activeTab" />

    <div class="pane-body">
      <PreviewPane v-if="activeTab === 'preview'" :artifact="activeArtifact" />
      <FileTreePane v-else-if="activeTab === 'files'" :task-id="taskId" />
      <DiffPane v-else-if="activeTab === 'diff'" :task-id="taskId" />
      <DownloadPane v-else :task-id="taskId" />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ArtifactTabs, { type ArtifactTabId } from './ArtifactTabs.vue'
import PreviewPane from './PreviewPane.vue'
import FileTreePane from './FileTreePane.vue'
import DiffPane from './DiffPane.vue'
import DownloadPane from './DownloadPane.vue'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'

const session = useSessionStore()
const workspace = useWorkspaceStore()

const activeTab = ref<ArtifactTabId>('preview')

const taskId = computed(() => workspace.activeTaskId)
const activeArtifact = computed(() => session.artifacts[0] ?? null)
</script>

<style scoped>
.sidebar-right {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border);
  background: #fff;
  min-width: 0;
}

.pane-body {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
</style>