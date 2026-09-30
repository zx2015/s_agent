<template>
  <McLayoutAside class="sidebar-left">
    <header class="sidebar-header">
      <div class="header-actions">
        <button class="new-task" @click="createTask">+ 新建任务</button>
        <button
          class="new-workspace"
          title="新建工作区"
          @click="createWorkspace"
        >
          <span class="icon-add-directory" />
        </button>
      </div>
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
  </McLayoutAside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { McLayoutAside } from '@matechat/core'
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

/**
 * The other way to pick a workspace for a task — via `WorkspaceTree.vue`'s
 * per-group "+" button — only works for workspaces that already exist.
 * This is what actually creates a new one to target.
 */
async function createWorkspace(): Promise<void> {
  const name = window.prompt('新工作区的名称：')
  if (!name || !name.trim()) return
  await store.createWorkspaceRemote(name.trim())
}
</script>

<style scoped>
/*
 * McLayoutAside's own CSS (@matechat/core/Layout/index.css) sets
 * `flex-direction: row`, meant for asides that lay out a row of icons.
 * Our sidebar is a vertical stack (header / tree / footer), which is a
 * legitimately different use of the same semantic wrapper — the
 * `!important` documents that this is a deliberate override, not an
 * accidental specificity fight.
 */
.sidebar-left {
  height: 100%;
  display: flex;
  flex-direction: column !important;
  border-right: 1px solid var(--color-border);
  background: #fff;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.header-actions {
  display: flex;
  gap: 6px;
}

.new-task {
  flex: 1;
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

.new-workspace {
  flex-shrink: 0;
  width: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 15px;
}

.new-workspace:hover {
  background: var(--color-bg-subtle);
  color: #165dff;
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
