<template>
  <div class="diff-pane">
    <div class="diff-toolbar">
      <button class="toolbar-action" @click="reload">刷新</button>
      <span class="diff-hint">{{ summary }}</span>
    </div>
    <pre v-if="diff" class="diff-content">{{ diff }}</pre>
    <p v-else class="empty">工作区没有未提交的变更</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps<{ taskId: string | null }>()

const diff = ref('')

const summary = computed(() => {
  if (!diff.value) return '无变更'
  const added = (diff.value.match(/^\+[^+]/gm) ?? []).length
  const removed = (diff.value.match(/^-[^-]/gm) ?? []).length
  return `+${added} / -${removed}`
})

async function reload(): Promise<void> {
  if (!props.taskId) {
    diff.value = ''
    return
  }
  try {
    const response = await fetch(`/api/tasks/${props.taskId}/git-diff`)
    if (!response.ok) throw new Error(String(response.status))
    const body = await response.json()
    diff.value = body.diff ?? ''
  } catch {
    diff.value = ''
  }
}

onMounted(reload)
watch(() => props.taskId, reload)
</script>

<style scoped>
.diff-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.diff-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
}

.toolbar-action {
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}

.diff-hint {
  margin-left: auto;
  color: #86909c;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.diff-content {
  flex: 1;
  margin: 0;
  padding: 10px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: pre;
  background: var(--color-bg-subtle);
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 12px;
  margin-top: 24px;
}
</style>