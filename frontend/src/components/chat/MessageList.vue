<template>
  <div ref="scrollArea" class="message-list">
    <p
      v-if="store.messages.length === 0"
      data-test="empty-state"
      class="empty-state"
    >
      描述你想完成的任务，Agent 会规划步骤并执行。
    </p>

    <template v-for="message in store.messages" :key="message.id">
      <UserMessage v-if="message.role === 'user'" :text="message.text" />
      <AssistantMessage v-else :message="message" />
    </template>

    <HitlConfirmCard
      v-if="store.pendingConfirm"
      :confirm="store.pendingConfirm"
      @allow="confirmToolCall('allow')"
      @deny="confirmToolCall('deny')"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import HitlConfirmCard from './HitlConfirmCard.vue'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const { confirmToolCall } = useChat()

const store = useSessionStore()
const scrollArea = ref<HTMLElement | null>(null)

// Follow the stream: without this the newest tokens render below the fold
// and the user has to chase the output with the scrollbar.
watch(
  () => [
    store.messages.length,
    store.messages[store.messages.length - 1]?.text,
    store.pendingConfirm,
  ],
  async () => {
    await nextTick()
    if (scrollArea.value) {
      scrollArea.value.scrollTop = scrollArea.value.scrollHeight
    }
  },
  { deep: true },
)
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.empty-state {
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
  margin-top: 48px;
}
</style>