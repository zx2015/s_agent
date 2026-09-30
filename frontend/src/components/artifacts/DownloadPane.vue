<template>
  <div class="download-pane">
    <p v-if="artifacts.length === 0" class="empty">暂无产物</p>

    <ul v-else class="artifact-list">
      <li
        v-for="artifact in artifacts"
        :key="artifact.filePath"
        class="artifact-item"
      >
        <span class="artifact-icon">{{ iconFor(artifact.type) }}</span>
        <span class="artifact-name">{{ artifact.filePath }}</span>
        <a
          class="download-link"
          :href="artifact.url"
          :download="artifact.filePath"
        >
          下载
        </a>
      </li>
    </ul>

    <footer v-if="artifacts.length > 0" class="pane-footer">
      <a class="download-all" :href="downloadAllUrl">打包下载全部</a>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/store/session'
import type { Artifact } from '@/types'

const props = defineProps<{ taskId: string | null }>()

const session = useSessionStore()
const artifacts = computed(() => session.artifacts)
const downloadAllUrl = computed(
  () => `/api/tasks/${props.taskId}/artifacts/download`,
)

function iconFor(type: Artifact['type']): string {
  switch (type) {
    case 'html':
      return '⬡'
    case 'markdown':
      return '¶'
    case 'image':
      return '▣'
    default:
      return '▤'
  }
}
</script>

<style scoped>
.download-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
}

.artifact-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-y: auto;
}

.artifact-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 6px;
  font-size: 12px;
}

.artifact-item:hover {
  background: var(--color-bg-subtle);
}

.artifact-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-link {
  color: #165dff;
  text-decoration: none;
}

.pane-footer {
  border-top: 1px solid var(--color-border);
  padding-top: 8px;
}

.download-all {
  display: block;
  text-align: center;
  padding: 6px;
  color: #165dff;
  text-decoration: none;
  font-size: 12px;
}

.empty {
  text-align: center;
  color: var(--color-text-muted);
  font-size: 12px;
  margin-top: 24px;
}
</style>