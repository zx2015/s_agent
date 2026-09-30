<template>
  <McLayout class="sidebar-middle">
    <McLayoutHeader>
      <TaskHeaderBar />
    </McLayoutHeader>

    <McLayoutContent :auto-scroll="true" :show-scroll-arrow="true">
      <MessageList />
    </McLayoutContent>

    <McLayoutSender>
      <ChatInput :disabled="session.isStreaming" @send="send" @stop="stop" />
    </McLayoutSender>
  </McLayout>
</template>

<script setup lang="ts">
import { McLayout, McLayoutContent, McLayoutHeader, McLayoutSender } from '@matechat/core'
import TaskHeaderBar from './TaskHeaderBar.vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import { useSessionStore } from '@/store/session'
import { useChat } from '@/composables/useChat'

const session = useSessionStore()
const { send, stop } = useChat()
</script>

<style scoped>
/*
 * McLayout already sets `display:flex; flex-direction:column; flex:auto`
 * (see @matechat/core/Layout/index.css) — the height:100% here is the
 * only thing it doesn't provide, needed so the pane fills its Splitpanes
 * slot rather than collapsing to content height.
 */
.sidebar-middle {
  height: 100%;
  background: #fff;
  min-width: 0;
}
</style>
