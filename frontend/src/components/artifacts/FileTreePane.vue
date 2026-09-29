<template>
  <div class="file-tree">
    <p v-if="files.length === 0" class="empty">暂无文件</p>
    <ul v-else class="tree-list">
      <li
        v-for="file in files"
        :key="file.path"
        class="file-item"
        :class="{ active: file.path === selectedPath }"
        @click="selectedPath = file.path"
      >
        <span class="file-icon">{{ file.isDir ? '▸' : '·' }}</span>
        <span class="file-name">{{ file.path }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

interface FileEntry {
  path: string
  isDir: boolean
}

const props = defineProps<{ taskId: string | null }>()

const files = ref<FileEntry[]>([])
const selectedPath = ref('')

async function loadFiles(): Promise<void> {
  if (!props.taskId) {
    files.value = []
    return
  }
  try {
    const response = await fetch(`/api/tasks/${props.taskId}/files`)
    if (!response.ok) throw new Error(String(response.status))
    const body = await response.json()
    files.value = body.files ?? []
  } catch {
    files.value = []
  }
}

onMounted(loadFiles)
watch(() => props.taskId, loadFiles)
</script>

<style scoped>
.file-tree {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.tree-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.file-item {
  display: flex;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.file-item:hover {
  background: var(--color-bg-subtle);
}

.file-item.active {
  background: #e8f3ff;
  color: #165dff;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 12px;
  margin-top: 24px;
}
</style>