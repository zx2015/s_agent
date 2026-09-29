<template>
  <div v-if="text" class="thinking-block">
    <button class="thinking-toggle" @click="expanded = !expanded">
      <span class="chevron">{{ expanded ? '▾' : '▸' }}</span>
      <span>思考过程</span>
      <span class="char-count">{{ text.length }} 字</span>
    </button>
    <pre v-show="expanded" class="thinking-text">{{ text }}</pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ text: string }>()

const expanded = ref(false)
</script>

<style scoped>
.thinking-block {
  margin: 8px 0;
  border-left: 2px solid #e5e6eb;
  padding-left: 10px;
}

.thinking-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: #86909c;
  padding: 2px 0;
}

.char-count {
  font-size: 11px;
  color: #c9cdd4;
}

.thinking-text {
  margin: 6px 0 0;
  font-size: 12px;
  color: #4e5969;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  max-height: 240px;
  overflow-y: auto;
}
</style>