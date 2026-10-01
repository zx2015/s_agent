<template>
  <div class="preview-pane">
    <div v-if="!active" class="empty">选择左侧产物以预览</div>

    <template v-else>
      <div class="preview-toolbar">
        <span class="file-name">{{ active.filePath }}</span>
        <div class="toolbar-actions">
          <button
            v-if="active.type === 'markdown'"
            class="toolbar-btn"
            data-test="toggle-raw-btn"
            @click="isRawMode = !isRawMode"
          >
            {{ isRawMode ? '预览效果' : '查看源码' }}
          </button>
          <button
            v-if="active.type === 'markdown' || active.type === 'text'"
            class="toolbar-btn"
            data-test="copy-content-btn"
            @click="copyContent"
          >
            {{ copySuccess ? '已复制' : '复制内容' }}
          </button>
          <a
            class="toolbar-action"
            :href="openInNewTabUrl"
            target="_blank"
            rel="noopener"
            data-test="open-new-tab-link"
          >
            新标签打开
          </a>
        </div>
      </div>

      <iframe
        v-if="active.type === 'html'"
        class="preview-frame"
        :src="active.url"
        sandbox="allow-scripts allow-forms"
        title="产物预览"
      />

      <img
        v-else-if="active.type === 'image'"
        class="preview-image"
        :src="active.url"
        alt=""
      />

      <div
        v-else-if="active.type === 'markdown'"
        class="preview-markdown-container"
        data-test="preview-markdown"
      >
        <pre v-if="isRawMode" class="preview-markdown-raw" data-test="markdown-raw">{{ markdownSource }}</pre>
        <div v-else class="preview-markdown-body" data-test="markdown-rendered">
          <McMarkdownCard
            :content="markdownSource"
            :enable-mermaid="true"
          />
        </div>
      </div>

      <pre v-else class="preview-text">{{ textSource }}</pre>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { McMarkdownCard } from '@matechat/core'
import type { Artifact } from '@/types'

const props = defineProps<{
  artifact: Artifact | null
  taskId?: string | null
}>()

const markdownSource = ref('')
const textSource = ref('')
const isRawMode = ref(false)
const copySuccess = ref(false)

const effectiveTaskId = computed(() => {
  if (props.taskId) return props.taskId
  if (props.artifact?.url) {
    const match = props.artifact.url.match(/\/api\/tasks\/([^/]+)\//)
    if (match) return match[1]
  }
  return ''
})

const openInNewTabUrl = computed(() => {
  if (!props.artifact) return '#'
  if (props.artifact.type === 'markdown') {
    const params = new URLSearchParams({
      view: 'artifact',
      taskId: effectiveTaskId.value,
      filePath: props.artifact.filePath,
      type: props.artifact.type,
    })
    return `/?${params.toString()}`
  }
  return props.artifact.url
})

async function copyContent() {
  const content = props.artifact?.type === 'markdown' ? markdownSource.value : textSource.value
  if (!content) return
  try {
    await navigator.clipboard.writeText(content)
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 2000)
  } catch {
    // Clipboard API might be restricted in some iframe/test environments
  }
}

// Only HTML and images can be shown by reference; markdown and plain text
// have to be fetched and rendered inline.
watch(
  () => props.artifact,
  async (artifact) => {
    markdownSource.value = ''
    textSource.value = ''
    isRawMode.value = false
    copySuccess.value = false
    if (!artifact || (artifact.type !== 'markdown' && artifact.type !== 'text'))
      return

    try {
      const response = await fetch(artifact.url)
      const body = await response.text()
      if (artifact.type === 'markdown') {
        markdownSource.value = body
      } else {
        textSource.value = body
      }
    } catch {
      if (artifact.type === 'markdown') {
        markdownSource.value = '（读取失败）'
      } else {
        textSource.value = '（读取失败）'
      }
    }
  },
  { immediate: true },
)

const active = computed(() => props.artifact)
</script>

<style scoped>
.preview-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.empty {
  margin: 40px auto;
  color: var(--color-text-muted);
  font-size: 13px;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
  background: var(--color-bg);
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--color-text);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-btn {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  border-color: #5e7ce0;
  color: #5e7ce0;
}

.toolbar-action {
  font-size: 11px;
  color: #5e7ce0;
  text-decoration: none;
}

.toolbar-action:hover {
  text-decoration: underline;
}

.preview-frame {
  flex: 1;
  border: none;
  width: 100%;
  background: #fff;
}

.preview-image {
  max-width: 100%;
  margin: 12px;
}

.preview-markdown-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-markdown-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--color-text);
  background: var(--color-bg);
}

.preview-markdown-body :deep(h1),
.preview-markdown-body :deep(h2),
.preview-markdown-body :deep(h3),
.preview-markdown-body :deep(h4) {
  margin-top: 20px;
  margin-bottom: 12px;
  color: var(--color-text);
  font-weight: 600;
}

.preview-markdown-body :deep(h1) {
  font-size: 20px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 8px;
}

.preview-markdown-body :deep(h2) {
  font-size: 17px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 6px;
}

.preview-markdown-body :deep(h3) {
  font-size: 15px;
}

.preview-markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 16px 0;
  font-size: 13px;
}

.preview-markdown-body :deep(th),
.preview-markdown-body :deep(td) {
  border: 1px solid var(--color-border);
  padding: 8px 12px;
  text-align: left;
}

.preview-markdown-body :deep(th) {
  background: var(--color-bg-subtle);
  font-weight: 600;
}

.preview-markdown-body :deep(pre) {
  background: var(--color-bg-subtle);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}

.preview-markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.preview-markdown-body :deep(blockquote) {
  margin: 14px 0;
  padding: 8px 16px;
  border-left: 4px solid var(--color-user-bubble-bg, #95ec69);
  background: var(--color-bg-subtle);
  border-radius: 0 4px 4px 0;
}

.preview-markdown-raw,
.preview-text {
  flex: 1;
  margin: 0;
  padding: 16px;
  overflow: auto;
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--color-bg-subtle);
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>