<template>
  <McBubble
    class="assistant-bubble"
    align="left"
    variant="none"
    :loading="message.streaming && !message.text && message.toolCalls.length === 0"
  >
    <ThinkingBlock :text="message.thinking" />
    <ToolCallCard
      v-for="call in message.toolCalls"
      :key="call.callId"
      :call="call"
    />
    <div
      v-if="message.text"
      class="assistant-text"
      data-test="assistant-text"
      v-html="renderedText"
    />
    <span v-if="message.streaming && message.text" class="cursor" />
  </McBubble>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { McBubble } from '@matechat/core'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatMessage } from '@/types'

const props = defineProps<{ message: ChatMessage }>()

const md = new MarkdownIt({
  html: false, // agent output is untrusted; never allow raw HTML
  linkify: true,
  breaks: true,
  highlight(code, language) {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return ''
  },
})

const renderedText = computed(() => md.render(props.message.text))
</script>

<style scoped>
.assistant-bubble {
  margin: 12px 0;
}

.assistant-bubble :deep(.mc-bubble-content) {
  font-size: 14px;
  line-height: 1.7;
  color: #1d2129;
}

.assistant-text :deep(pre) {
  background: var(--color-bg-subtle);
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
}

.assistant-text :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 14px;
  background: #165dff;
  animation: blink 1s step-end infinite;
  vertical-align: text-bottom;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
