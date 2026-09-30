<template>
  <div class="chat-input">
    <McInput
      :value="draft"
      :placeholder="placeholder"
      :disabled="false"
      :loading="disabled"
      :max-length="4000"
      show-count
      auto-clear
      @change="draft = $event"
      @submit="submit"
      @cancel="emit('stop')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { McInput } from '@matechat/core'

const props = defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ send: [message: string]; stop: [] }>()

const draft = ref('')

const placeholder = computed(() =>
  props.disabled
    ? 'Agent 正在工作…'
    : '描述你的任务，Enter 发送，Shift+Enter 换行',
)

/**
 * `McInput`'s own `disabled` would grey out the whole field while
 * streaming; the workbench only wants the *send* action replaced by a
 * stop action, so the field itself stays interactive and `loading` is
 * used instead to flip the send button into its cancel state, which
 * emits `cancel` -> `stop`.
 */
function submit(text: string): void {
  const trimmed = text.trim()
  if (!trimmed || props.disabled) return
  emit('send', trimmed)
}
</script>

<style scoped>
.chat-input {
  padding: 12px 24px 16px;
  border-top: 1px solid var(--color-border);
}
</style>
