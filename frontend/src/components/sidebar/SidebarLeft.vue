<template>
  <aside class="sidebar-left">
    <header class="sidebar-header">
      <button class="new-task" @click="createTask">+ 新建任务</button>
      <input
        v-model="query"
        class="search-input"
        placeholder="搜索任务"
        type="search"
      />
    </header>

    <WorkspaceTree />

    <footer class="sidebar-footer">
      <button class="user-button" @click="settings.openDrawer()">
        <span class="avatar">A</span>
        <span class="user-name">用户</span>
        <span class="settings-icon">⚙</span>
      </button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import WorkspaceTree from './WorkspaceTree.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSettingsStore } from '@/store/settings'

const store = useWorkspaceStore()
const settings = useSettingsStore()

const query = computed({
  get: () => store.searchQuery,
  set: (value: string) => store.setSearchQuery(value),
})

async function createTask(): Promise<void> {
  const target = store.workspaces[0]
  const workspaceId = target?.id ?? 'default'
  const task = await store.createTaskRemote(workspaceId, '新任务')
  store.selectTask(task.id)
}
</script>

<style scoped>
.sidebar-left {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  background: #fff;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.new-task {
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.new-task:hover {
  background: var(--color-bg-subtle);
}

.search-input {
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
}

.sidebar-footer {
  border-top: 1px solid var(--color-border);
  padding: 8px;
}

.user-button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.user-button:hover {
  background: var(--color-bg-subtle);
}

.avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #165dff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.user-name {
  flex: 1;
  text-align: left;
}
</style>
