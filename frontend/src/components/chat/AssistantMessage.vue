<template>
  <McBubble
    class="assistant-bubble"
    align="left"
    variant="none"
    :loading="message.streaming && !message.text && message.toolCalls.length === 0 && (!message.blocks || message.blocks.length === 0)"
  >
    <!-- Chronologically ordered blocks (thinking, tool_call, text) -->
    <template v-if="message.blocks && message.blocks.length > 0">
      <template v-for="(block, index) in message.blocks" :key="index">
        <ThinkingBlock v-if="block.type === 'thinking'" :text="block.content" />
        <ToolCallCard v-else-if="block.type === 'tool_call'" :call="block.call" />
        <div v-else-if="block.type === 'text' && block.content" class="assistant-text" data-test="assistant-text">
          <McMarkdownCard :content="block.content" />
        </div>
      </template>
    </template>

    <!-- Fallback for historical messages without blocks -->
    <template v-else>
      <ThinkingBlock :text="message.thinking" />
      <ToolCallCard
        v-for="call in message.toolCalls"
        :key="call.callId"
        :call="call"
      />
      <div v-if="message.text" class="assistant-text" data-test="assistant-text">
        <McMarkdownCard :content="message.text" />
      </div>
    </template>

    <span v-if="message.streaming && (message.text || (message.blocks && message.blocks.length > 0))" class="cursor" />

    <!-- Copy is shown once the answer has actually finished -->
    <McToolbar
      v-if="!message.streaming && message.text"
      class="assistant-toolbar"
      :items="[{ key: 'copy', icon: ToolbarAction.COPY, text: message.text, label: '复制' }]"
    />
  </McBubble>
</template>

<script setup lang="ts">
import { McBubble, McMarkdownCard, McToolbar } from '@matechat/core'
import { ToolbarAction } from '@matechat/core/Toolbar'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallCard from './ToolCallCard.vue'
import type { ChatMessage } from '@/types'

defineProps<{ message: ChatMessage }>()
</script>

<style scoped>
.assistant-bubble {
  margin: 12px 0;
}

.assistant-bubble :deep(.mc-bubble-content) {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text);
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

.assistant-toolbar {
  margin-top: 4px;
  opacity: 0.6;
}

.assistant-toolbar:hover {
  opacity: 1;
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
