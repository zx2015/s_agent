<template>
  <div class="chat-input">
    <textarea
      ref="textarea"
      v-model="draft"
      class="input-area"
      :placeholder="placeholder"
      :disabled="disabled"
      rows="1"
      @keydown.enter.exact.prevent="submit"
      @input="autoGrow"
    />
    <button
      v-if="!disabled"
      class="send-button"
      :disabled="!canSend"
      @click="submit"
    >
      发送
    </button>
    <button v-else class="send-button stop" @click="emit('stop')">
      停止生成
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

const props = defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ send: [message: string]; stop: [] }>()

const draft = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

const canSend = computed(() => draft.value.trim().length > 0)
const placeholder = computed(() =>
  props.disabled
    ? 'Agent 正在工作…'
    : '描述你的任务，Enter 发送，Shift+Enter 换行',
)

function autoGrow(): void {
  const element = textarea.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 160)}px`
}

function submit(): void {
  if (!canSend.value || props.disabled) return
  emit('send', draft.value.trim())
  draft.value = ''
  nextTick(autoGrow)
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--color-border);
}

.input-area {
  flex: 1;
  resize: none;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  max-height: 160px;
}

.input-area:focus {
  outline: none;
  border-color: #165dff;
}

.send-button {
  padding: 10px 18px;
  border: none;
  border-radius: 8px;
  background: #165dff;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  flex-shrink: 0;
}

.send-button:disabled {
  background: #c9cdd4;
  cursor: not-allowed;
}

.send-button.stop {
  background: #f53f3f;
}
</style>