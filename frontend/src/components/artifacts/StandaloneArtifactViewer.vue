<template>
  <div class="standalone-viewer">
    <header class="viewer-header">
      <div class="header-left">
        <a class="back-link" href="/" title="返回智能体工作台">
          <span class="back-icon">←</span>
          <span class="back-text">返回工作台</span>
        </a>
        <span class="divider">/</span>
        <span class="file-icon">📄</span>
        <span class="file-title" :title="filePath">{{ filePath }}</span>
        <span class="badge">{{ type || 'markdown' }}</span>
      </div>

      <div class="header-right">
        <button
          class="btn"
          data-test="standalone-toggle-raw"
          @click="isRawMode = !isRawMode"
        >
          {{ isRawMode ? '预览效果' : '查看源码' }}
        </button>
        <button
          class="btn"
          data-test="standalone-copy"
          @click="copyContent"
        >
          {{ copySuccess ? '已复制' : '复制内容' }}
        </button>
        <a
          class="btn btn-primary"
          :href="downloadUrl"
          :download="fileName"
        >
          下载文件
        </a>
        <button
          class="btn btn-icon"
          title="切换深浅主题"
          @click="toggleTheme"
        >
          {{ settings.theme === 'dark' ? '☀️' : '🌙' }}
        </button>
      </div>
    </header>

    <main class="viewer-body">
      <div v-if="isLoading" class="state-box loading">
        <span>正在加载产物内容...</span>
      </div>

      <div v-else-if="isError" class="state-box error">
        <p>无法读取产物文件（{{ filePath }}）</p>
        <button class="btn" @click="loadFile">重试</button>
      </div>

      <div v-else class="content-wrapper">
        <pre v-if="isRawMode" class="raw-view" data-test="standalone-raw">{{ content }}</pre>
        <div v-else class="markdown-view" data-test="standalone-rendered">
          <McMarkdownCard
            :content="content"
            :enable-mermaid="true"
          />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { McMarkdownCard } from '@matechat/core'
import { useSettingsStore } from '@/store/settings'

const props = withDefaults(
  defineProps<{
    taskId: string
    filePath: string
    type?: string
  }>(),
  {
    type: 'markdown',
  },
)

const settings = useSettingsStore()

const content = ref('')
const isLoading = ref(true)
const isError = ref(false)
const isRawMode = ref(false)
const copySuccess = ref(false)

const fileName = computed(() => {
  const parts = props.filePath.split('/')
  return parts[parts.length - 1] || props.filePath
})

const downloadUrl = computed(() => {
  return `/api/tasks/${encodeURIComponent(props.taskId)}/artifacts/preview/${props.filePath}`
})

async function loadFile(): Promise<void> {
  if (!props.taskId || !props.filePath) {
    isLoading.value = false
    isError.value = true
    return
  }

  isLoading.value = true
  isError.value = false

  try {
    const res = await fetch(downloadUrl.value)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    content.value = await res.text()
  } catch {
    isError.value = true
  } finally {
    isLoading.value = false
  }
}

async function copyContent(): Promise<void> {
  if (!content.value) return
  try {
    await navigator.clipboard.writeText(content.value)
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 2000)
  } catch {
    // Clipboard permission fallback
  }
}

function toggleTheme(): void {
  settings.setTheme(settings.theme === 'dark' ? 'light' : 'dark')
}

onMounted(loadFile)
</script>

<style scoped>
.standalone-viewer {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}

.viewer-header {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.back-link {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #5e7ce0;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.2s;
}

.back-link:hover {
  opacity: 0.8;
}

.divider {
  color: var(--color-text-muted);
  font-size: 13px;
}

.file-icon {
  font-size: 15px;
}

.file-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 480px;
}

.badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  color: var(--color-text);
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}

.btn:hover {
  border-color: #5e7ce0;
  color: #5e7ce0;
}

.btn-primary {
  background: #5e7ce0;
  border-color: #5e7ce0;
  color: #fff;
}

.btn-primary:hover {
  background: #4a67cb;
  color: #fff;
}

.btn-icon {
  padding: 5px 8px;
  font-size: 14px;
}

.viewer-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.state-box {
  margin: 60px auto;
  text-align: center;
  font-size: 14px;
  color: var(--color-text-muted);
}

.state-box.error {
  color: #f56c6c;
}

.state-box.error p {
  margin-bottom: 16px;
}

.content-wrapper {
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  padding: 32px 24px 64px;
  box-sizing: border-box;
}

.raw-view {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  font-size: 13px;
  line-height: 1.6;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.markdown-view {
  font-size: 15px;
  line-height: 1.8;
}

.markdown-view :deep(h1),
.markdown-view :deep(h2),
.markdown-view :deep(h3),
.markdown-view :deep(h4) {
  margin-top: 28px;
  margin-bottom: 14px;
  color: var(--color-text);
  font-weight: 600;
}

.markdown-view :deep(h1) {
  font-size: 24px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 10px;
}

.markdown-view :deep(h2) {
  font-size: 20px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 8px;
}

.markdown-view :deep(h3) {
  font-size: 17px;
}

.markdown-view :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 20px 0;
  font-size: 14px;
}

.markdown-view :deep(th),
.markdown-view :deep(td) {
  border: 1px solid var(--color-border);
  padding: 10px 14px;
  text-align: left;
}

.markdown-view :deep(th) {
  background: var(--color-bg-subtle);
  font-weight: 600;
}

.markdown-view :deep(pre) {
  background: var(--color-bg-subtle);
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-view :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.markdown-view :deep(blockquote) {
  margin: 16px 0;
  padding: 10px 18px;
  border-left: 4px solid var(--color-user-bubble-bg, #95ec69);
  background: var(--color-bg-subtle);
  border-radius: 0 6px 6px 0;
}
</style>
