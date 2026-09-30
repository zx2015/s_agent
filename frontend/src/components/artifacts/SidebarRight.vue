<template>
  <McLayoutAside class="sidebar-right">
    <ArtifactTabs v-model:active-tab="activeTab" />

    <div class="pane-body">
      <PreviewPane v-if="activeTab === 'preview'" :artifact="activeArtifact" />
      <FileTreePane v-else-if="activeTab === 'files'" :task-id="taskId" />
      <DiffPane v-else-if="activeTab === 'diff'" :task-id="taskId" />
      <DownloadPane v-else :task-id="taskId" />
    </div>
  </McLayoutAside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { McLayoutAside } from '@matechat/core'
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
/* See SidebarLeft.vue for why this overrides McLayoutAside's default
   `flex-direction: row`. */
.sidebar-right {
  height: 100%;
  display: flex;
  flex-direction: column !important;
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