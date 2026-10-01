<template>
  <div class="tool-call" :class="`status-${call.status}`">
    <header class="tool-header">
      <span class="tool-icon">{{ statusIcon }}</span>
      <span class="tool-name">{{ toolDisplayName }}</span>
      <span class="tool-status">{{ statusLabel }}</span>
    </header>
    <pre class="tool-args">{{ argsPreview }}</pre>
    <pre v-if="call.summary" class="tool-result">{{ call.summary }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ToolCallRecord } from '@/types'

const props = defineProps<{ call: ToolCallRecord }>()

const toolDisplayName = computed(() => {
  if (props.call.tool === 'delegate_task') {
    const role = props.call.args.role ? ` (${props.call.args.role})` : ''
    return `子智能体委派${role}`
  }
  return props.call.tool
})

const statusIcon = computed(() => {
  switch (props.call.status) {
    case 'running':
      return '◌'
    case 'success':
      return '✓'
    default:
      return '✕'
  }
})

const statusLabel = computed(() => {
  switch (props.call.status) {
    case 'running':
      return '执行中'
    case 'success':
      return '完成'
    default:
      return '失败'
  }
})

const argsPreview = computed(() => {
  const entries = Object.entries(props.call.args)
  if (entries.length === 0) return ''
  return entries
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join('\n')
})
</script>

<style scoped>
.tool-call {
  margin: 8px 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--color-bg-subtle);
  font-size: 12px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-name {
  font-weight: 600;
  color: #1d2129;
}

.tool-status {
  margin-left: auto;
  color: var(--color-text-muted);
}

.status-success .tool-icon {
  color: #00b42a;
}

.status-error .tool-icon {
  color: #f53f3f;
}

.status-running .tool-icon {
  color: #165dff;
}

.tool-args,
.tool-result {
  margin: 6px 0 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  color: #4e5969;
  max-height: 160px;
  overflow-y: auto;
}
</style>