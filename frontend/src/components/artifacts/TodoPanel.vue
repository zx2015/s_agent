<template>
  <div class="todo-panel">
    <header v-if="visibleTodos.length > 0" class="panel-header">
      <span class="summary">{{ store.summary }}</span>
      <label v-if="hasDeleted" class="show-deleted">
        <input v-model="showDeleted" type="checkbox" />
        <span>显示已删除 ({{ deletedCount }})</span>
      </label>
    </header>

    <div v-if="visibleTodos.length === 0" class="empty">
      <p>暂无待办任务</p>
      <span class="hint">Agent 执行多步骤任务时，会在此规划步骤。</span>
    </div>

    <ul v-else class="todo-list">
      <li
        v-for="item in visibleTodos"
        :key="item.id"
        class="todo-item"
        :class="[`state-${item.state}`]"
      >
        <span class="state-icon" :title="item.state">
          {{ stateIcon(item.state) }}
        </span>

        <div class="item-body">
          <div class="item-header">
            <span class="item-id">#{{ item.id }}</span>
            <span class="item-subject">{{ item.subject }}</span>
            <span v-if="item.owner" class="item-owner">@{{ item.owner }}</span>
          </div>

          <p v-if="item.description" class="item-desc">
            {{ item.description }}
          </p>

          <div v-if="item.blockedBy.length > 0" class="item-deps">
            <span class="dep-label">
              阻塞于 {{ item.blockedBy.map((id) => `#${id}`).join(', ') }}
            </span>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTodosStore } from '@/store/todos'
import type { TodoItem, TodoState } from '@/types'

const store = useTodosStore()
const showDeleted = ref(false)

const hasDeleted = computed(() =>
  store.todos.some((t) => t.state === 'deleted'),
)

const deletedCount = computed(
  () => store.todos.filter((t) => t.state === 'deleted').length,
)

const visibleTodos = computed<TodoItem[]>(() => {
  if (showDeleted.value) return store.todos
  return store.todos.filter((t) => t.state !== 'deleted')
})

function stateIcon(state: TodoState): string {
  switch (state) {
    case 'completed':
      return '✓'
    case 'in_progress':
      return '⏳'
    case 'deleted':
      return '✕'
    case 'pending':
    default:
      return '○'
  }
}
</script>

<style scoped>
.todo-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 8px;
  font-size: 12px;
}

.summary {
  font-weight: 600;
  color: var(--color-text);
}

.show-deleted {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-muted);
  cursor: pointer;
}

.empty {
  margin: 40px auto;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}

.empty .hint {
  display: block;
  font-size: 11px;
  margin-top: 4px;
}

.todo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.todo-item {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  transition: border-color 0.15s ease;
}

.todo-item.state-in_progress {
  border-color: #165dff;
  background: #f2f7ff;
}

.todo-item.state-completed {
  border-color: #e5e6eb;
  background: var(--color-bg-subtle);
  opacity: 0.85;
}

.todo-item.state-completed .item-subject {
  text-decoration: line-through;
  color: var(--color-text-muted);
}

.todo-item.state-deleted {
  opacity: 0.5;
  border-style: dashed;
}

.state-icon {
  font-size: 14px;
  line-height: 1.2;
  flex-shrink: 0;
}

.state-completed .state-icon {
  color: #00b42a;
}

.state-in_progress .state-icon {
  color: #165dff;
}

.state-pending .state-icon {
  color: var(--color-text-muted);
}

.state-deleted .state-icon {
  color: #f53f3f;
}

.item-body {
  flex: 1;
  min-width: 0;
}

.item-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.item-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--color-text-muted);
  font-weight: 600;
}

.item-subject {
  font-weight: 500;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-owner {
  margin-left: auto;
  font-size: 11px;
  color: #165dff;
}

.item-desc {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.4;
}

.item-deps {
  margin-top: 4px;
  font-size: 10px;
  color: #ff7d00;
}
</style>