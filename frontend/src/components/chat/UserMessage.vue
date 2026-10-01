<template>
  <McBubble class="user-bubble" align="right" variant="filled" :content="text" />
</template>

<script setup lang="ts">
import { McBubble } from '@matechat/core'

defineProps<{ text: string }>()
</script>

<style scoped>
.user-bubble {
  margin: 12px 0;
}

.user-bubble :deep(.mc-bubble-content) {
  background-color: var(--color-user-bubble-bg, #95ec69) !important;
  color: var(--color-user-bubble-text, #191919) !important;
  border: 1px solid var(--color-user-bubble-border, #85d658) !important;
  border-radius: 8px !important;
  padding: 10px 14px !important;
  font-size: 14px !important;
  line-height: 1.6 !important;
  white-space: pre-wrap;
  word-break: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.user-bubble :deep(.mc-bubble-content *) {
  color: inherit !important;
}
</style>
