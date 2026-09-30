<template>
  <div class="message-list">
    <McIntroduction
      v-if="store.messages.length === 0"
      data-test="empty-state"
      title="MateChat 工作台"
      sub-title="描述你想完成的任务，Agent 会规划步骤并执行"
      :description="[
        '可以读写文件、执行命令、生成网页，也能做精确计算',
      ]"
    >
      <McPrompt :list="suggestions" @item-click="onSuggestionClick" />
    </McIntroduction>

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
import { McIntroduction, McPrompt } from '@matechat/core'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import HitlConfirmCard from './HitlConfirmCard.vue'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const { confirmToolCall, send } = useChat()

const store = useSessionStore()

/** Shape of `McPrompt`'s `list` prop items (@matechat/core/Prompt). */
interface PromptItem {
  value: string | number
  label: string
}

// Onboarding shortcuts mirroring the tool capabilities described in the
// backend's system prompt (server/agent/core.py) — clicking one runs it
// immediately rather than just filling the input, since these are meant
// to demonstrate the agent working, not just show example phrasing.
const suggestions: PromptItem[] = [
  { value: 'html-page', label: '写一个个人主页的 HTML 页面' },
  { value: 'calc', label: '帮我算一下 (153.2 - 100) / 100 * 100' },
  { value: 'read-files', label: '看看当前工作区里有哪些文件' },
]

function onSuggestionClick(prompt: PromptItem): void {
  send(prompt.label)
}
</script>

<style scoped>
.message-list {
  padding: 16px 24px;
}
</style>
