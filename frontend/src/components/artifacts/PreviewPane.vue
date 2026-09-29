<template>
  <div class="preview-pane">
    <div v-if="!active" class="empty">选择左侧产物以预览</div>

    <template v-else>
      <div class="preview-toolbar">
        <span class="file-name">{{ active.filePath }}</span>
        <a
          class="toolbar-action"
          :href="active.url"
          target="_blank"
          rel="noopener"
        >
          新标签打开
        </a>
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

      <pre
        v-else-if="active.type === 'markdown'"
        class="preview-markdown"
      >{{ markdownSource }}</pre>

      <pre v-else class="preview-text">{{ textSource }}</pre>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Artifact } from '@/types'

const props = defineProps<{ artifact: Artifact | null }>()

const markdownSource = ref('')
const textSource = ref('')

// Only HTML and images can be shown by reference; markdown and plain text
// have to be fetched and rendered inline.
watch(
  () => props.artifact,
  async (artifact) => {
    markdownSource.value = ''
    textSource.value = ''
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
      textSource.value = '（读取失败）'
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
  color: #86909c;
  font-size: 13px;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #4e5969;
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

.preview-markdown,
.preview-text {
  flex: 1;
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>