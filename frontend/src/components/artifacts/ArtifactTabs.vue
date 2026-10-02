<template>
  <nav class="artifact-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      class="tab"
      :class="{ active: tab.id === activeTab }"
      @click="emit('update:activeTab', tab.id)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<script setup lang="ts">
export type ArtifactTabId = 'todos' | 'files'

defineProps<{ activeTab: ArtifactTabId }>()
const emit = defineEmits<{ 'update:activeTab': [tab: ArtifactTabId] }>()

const tabs: Array<{ id: ArtifactTabId; label: string }> = [
  { id: 'todos', label: '待办' },
  { id: 'files', label: '全部文件' },
]
</script>

<style scoped>
.artifact-tabs {
  display: flex;
  border-bottom: 1px solid var(--color-border);
  padding: 0 4px;
}

.tab {
  padding: 8px 10px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 12px;
  color: #4e5969;
  cursor: pointer;
}

.tab.active {
  color: #165dff;
  border-bottom-color: #165dff;
}
</style>