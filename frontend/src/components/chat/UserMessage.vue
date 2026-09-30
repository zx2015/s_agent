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
  background: #165dff;
  color: #fff;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
