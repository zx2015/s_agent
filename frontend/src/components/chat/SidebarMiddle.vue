<template>
  <section class="sidebar-middle">
    <TaskHeaderBar />
    <MessageList />
    <ChatInput
      :disabled="session.isStreaming"
      @send="send"
      @stop="stop"
    />
  </section>
</template>

<script setup lang="ts">
import TaskHeaderBar from './TaskHeaderBar.vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const session = useSessionStore()
const { send, stop } = useChat()
</script>

<style scoped>
.sidebar-middle {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  min-width: 0;
}
</style>