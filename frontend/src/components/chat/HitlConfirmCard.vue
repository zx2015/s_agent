<template>
  <div class="hitl-card">
    <header class="hitl-header">
      <span class="hitl-icon">⚠</span>
      <span>需要你的确认</span>
    </header>
    <p class="hitl-reason">{{ confirm.reason }}</p>
    <pre class="hitl-command">{{ confirm.command }}</pre>
    <footer class="hitl-actions">
      <button class="btn btn-deny" @click="emit('deny')">拒绝</button>
      <button class="btn btn-allow" @click="emit('allow')">允许执行</button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import type { PendingConfirm } from '@/types'

defineProps<{ confirm: PendingConfirm }>()

const emit = defineEmits<{ allow: []; deny: [] }>()
</script>

<style scoped>
.hitl-card {
  margin: 12px 0;
  border: 1px solid #ff7d00;
  border-radius: 8px;
  padding: 12px;
  background: #fff7e8;
}

.hitl-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #d25f00;
}

.hitl-reason {
  margin: 8px 0 4px;
  font-size: 13px;
  color: #4e5969;
}

.hitl-command {
  margin: 0;
  padding: 8px;
  background: #fff;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.hitl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: #fff;
}

.btn-allow {
  background: #165dff;
  border-color: #165dff;
  color: #fff;
}

.btn-deny:hover {
  background: var(--color-bg-subtle);
}
</style>