<template>
  <div ref="listRef" class="message-list">
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

    <div
      v-if="store.hasMoreHistory"
      class="history-loader"
      data-test="history-loader"
    >
      <button
        class="load-more-btn"
        :disabled="store.isLoadingMoreHistory"
        data-test="load-more-btn"
        @click="handleLoadMore"
      >
        <span v-if="store.isLoadingMoreHistory" class="loading-spinner" />
        <span v-else class="icon-clock">⏱</span>
        <span>
          {{
            store.isLoadingMoreHistory
              ? '正在加载更早历史...'
              : `加载更早历史消息 (还有 ${store.remainingHistoryCount} 条)`
          }}
        </span>
      </button>
    </div>

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
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { McIntroduction, McPrompt } from '@matechat/core'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import HitlConfirmCard from './HitlConfirmCard.vue'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const { confirmToolCall, send } = useChat()

const store = useSessionStore()
const listRef = ref<HTMLDivElement | null>(null)

async function handleLoadMore(): Promise<void> {
  const scroller = listRef.value?.closest('.mc-layout-content-scroller') as HTMLElement | null
  const prevScrollHeight = scroller ? scroller.scrollHeight : 0
  const prevScrollTop = scroller ? scroller.scrollTop : 0

  const loaded = await store.loadMoreHistory()
  if (loaded && scroller) {
    await nextTick()
    const heightDiff = scroller.scrollHeight - prevScrollHeight
    scroller.scrollTop = prevScrollTop + heightDiff
  }
}

function onScroll(e: Event): void {
  const el = e.target as HTMLElement | null
  if (!el) return
  if (el.scrollTop < 60 && store.hasMoreHistory && !store.isLoadingMoreHistory) {
    handleLoadMore()
  }
}

onMounted(() => {
  const scroller = listRef.value?.closest('.mc-layout-content-scroller')
  if (scroller) {
    scroller.addEventListener('scroll', onScroll, { passive: true })
  }
})

onUnmounted(() => {
  const scroller = listRef.value?.closest('.mc-layout-content-scroller')
  if (scroller) {
    scroller.removeEventListener('scroll', onScroll)
  }
})

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

.history-loader {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px 0 16px 0;
}

.load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background-color: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  font-size: 12px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}

.load-more-btn:hover:not(:disabled) {
  background-color: #e2e8f0;
  color: #0f172a;
  border-color: #cbd5e1;
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.icon-clock {
  font-size: 12px;
}

.loading-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid #94a3b8;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

