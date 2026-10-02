<template>
  <McLayoutAside class="sidebar-right">
    <ArtifactTabs v-model:active-tab="activeTab" />

    <div class="pane-body">
      <TodoPanel v-if="activeTab === 'todos'" />
      <FileTreePane v-else-if="activeTab === 'files'" :task-id="taskId" />
    </div>
  </McLayoutAside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { McLayoutAside } from '@matechat/core'
import ArtifactTabs, { type ArtifactTabId } from './ArtifactTabs.vue'
import TodoPanel from './TodoPanel.vue'
import FileTreePane from './FileTreePane.vue'
import { useWorkspaceStore } from '@/store/workspaces'

const workspace = useWorkspaceStore()

const activeTab = ref<ArtifactTabId>('todos')

const taskId = computed(() => workspace.activeTaskId)

// Reset the active tab back to 'todos' whenever the user switches (or deletes) the active task.
watch(taskId, () => {
  activeTab.value = 'todos'
})
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