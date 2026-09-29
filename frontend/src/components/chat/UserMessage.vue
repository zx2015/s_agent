<template>
  <div class="user-message">
    <div class="bubble">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<style scoped>
.user-message {
  display: flex;
  justify-content: flex-end;
  margin: 12px 0;
}

.bubble {
  max-width: 70%;
  padding: 10px 14px;
  background: #165dff;
  color: #fff;
  border-radius: 12px 12px 2px 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>