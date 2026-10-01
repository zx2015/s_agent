<template>
  <McLayoutAside class="sidebar-left">
    <header class="sidebar-header">
      <button class="new-task" @click="openPanel">+ 新建任务</button>

      <div v-if="panelOpen" class="create-panel" data-test="create-panel">
        <label class="field">
          <span class="field-label">任务标题</span>
          <input
            v-model="draftTitle"
            class="field-input"
            placeholder="新任务"
            data-test="new-task-title"
            @keydown.enter="confirmCreate"
          />
        </label>

        <div class="field">
          <span class="field-label">文件夹</span>
          <div class="folder-picker" data-test="new-task-workspace">
            <button
              v-for="ws in store.workspaces"
              :key="ws.id"
              type="button"
              class="folder-row"
              :class="{ selected: selectedWorkspaceId === ws.id }"
              :data-test="`folder-option-${ws.id}`"
              @click="selectedWorkspaceId = ws.id"
            >
              <span class="icon-folder folder-icon" />
              <span class="folder-name">{{ ws.name }}</span>
            </button>
            <button
              type="button"
              class="folder-row new-folder-row"
              :class="{ selected: isCreatingNewWorkspace }"
              data-test="folder-option-new"
              @click="selectedWorkspaceId = NEW_WORKSPACE_OPTION"
            >
              <span class="icon-folder-new folder-icon" />
              <span class="folder-name">新建文件夹…</span>
            </button>
          </div>
        </div>

        <label v-if="isCreatingNewWorkspace" class="field">
          <span class="field-label">新文件夹名称</span>
          <input
            v-model="newWorkspaceName"
            class="field-input"
            placeholder="例如：股票分析"
            data-test="new-workspace-name"
            @keydown.enter="confirmCreate"
          />
        </label>

        <div class="panel-actions">
          <button class="panel-cancel" @click="closePanel">取消</button>
          <button
            class="panel-confirm"
            :disabled="isCreatingNewWorkspace && !newWorkspaceName.trim()"
            data-test="confirm-create"
            @click="confirmCreate"
          >
            创建
          </button>
        </div>
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
import { computed, ref, watch } from 'vue'
import { McLayoutAside } from '@matechat/core'
import WorkspaceTree from './WorkspaceTree.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSettingsStore } from '@/store/settings'
import { useSessionStore } from '@/store/session'
import { useTodosStore } from '@/store/todos'

const store = useWorkspaceStore()
const settings = useSettingsStore()
const session = useSessionStore()
const todos = useTodosStore()

const query = computed({
  get: () => store.searchQuery,
  set: (value: string) => store.setSearchQuery(value),
})

/**
 * Choosing/creating a folder used to be `window.prompt()` (see git
 * history) — dropped because native dialogs are easy to miss or get
 * silently blocked by some browsers/extensions, which made the
 * "+ 新建工作区" button look like it did nothing even though it worked
 * when actually clicked (verified with Playwright: the dialog did fire
 * and the POST did land). A real in-page panel can't be silently
 * dismissed that way, and folds "which folder" into task creation
 * itself instead of a separate, easy-to-miss button.
 */
const NEW_WORKSPACE_OPTION = '__new__'

const panelOpen = ref(false)
const draftTitle = ref('')
const selectedWorkspaceId = ref('default')
const newWorkspaceName = ref('')

const isCreatingNewWorkspace = computed(
  () => selectedWorkspaceId.value === NEW_WORKSPACE_OPTION,
)

function openPanel(): void {
  draftTitle.value = ''
  newWorkspaceName.value = ''
  selectedWorkspaceId.value =
    store.activeTask?.workspaceId ?? store.workspaces[0]?.id ?? 'default'
  panelOpen.value = true
}

function closePanel(): void {
  panelOpen.value = false
}

// If the selected workspace gets deleted out from under an open panel,
// fall back rather than submitting a dangling id.
watch(
  () => store.workspaces,
  (list) => {
    if (
      selectedWorkspaceId.value !== NEW_WORKSPACE_OPTION &&
      !list.some((ws) => ws.id === selectedWorkspaceId.value)
    ) {
      selectedWorkspaceId.value = list[0]?.id ?? 'default'
    }
  },
  { deep: true },
)

async function confirmCreate(): Promise<void> {
  let workspaceId = selectedWorkspaceId.value

  if (isCreatingNewWorkspace.value) {
    const name = newWorkspaceName.value.trim()
    if (!name) return
    const workspace = await store.createWorkspaceRemote(name)
    workspaceId = workspace.id
  }

  const title = draftTitle.value.trim() || '新任务'
  const task = await store.createTaskRemote(workspaceId, title)
  store.selectTask(task.id)
  session.switchToTask(task.id)
  todos.switchToTask(task.id)
  session.reset(task.id)
  todos.clear(task.id)
  closePanel()
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

.create-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-subtle);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.field-input {
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
}

.folder-picker {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  padding: 4px;
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: 5px;
  background: none;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
  color: inherit;
}

.folder-row:hover {
  background: var(--color-bg-subtle);
}

.folder-row.selected {
  background: #e8f3ff;
  color: #165dff;
}

.folder-icon {
  flex-shrink: 0;
  font-size: 15px;
  color: #ffb02e;
}

.folder-row.selected .folder-icon {
  color: #165dff;
}

.folder-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.new-folder-row {
  border-top: 1px dashed var(--color-border);
  margin-top: 2px;
  padding-top: 8px;
  color: var(--color-text-muted);
}

.new-folder-row .folder-icon {
  color: var(--color-text-muted);
}

.new-folder-row.selected {
  color: #165dff;
}

.new-folder-row.selected .folder-icon {
  color: #165dff;
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 2px;
}

.panel-cancel,
.panel-confirm {
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: #fff;
}

.panel-confirm {
  background: #165dff;
  border-color: #165dff;
  color: #fff;
}

.panel-confirm:disabled {
  background: #c9cdd4;
  border-color: #c9cdd4;
  cursor: not-allowed;
}

.panel-cancel:hover {
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
