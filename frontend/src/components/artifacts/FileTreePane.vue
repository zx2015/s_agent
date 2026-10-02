<template>
  <div class="file-tree">
    <p v-if="files.length === 0" class="empty">暂无文件</p>
    <ul v-else class="tree-list">
      <li
        v-for="item in visibleNodes"
        :key="item.path"
        class="tree-item"
        :class="{ 'is-dir': item.isDir, 'is-file': !item.isDir }"
        :style="{ paddingLeft: `${item.depth * 16 + 8}px` }"
        :data-test="`tree-item-${item.path}`"
        @click="item.isDir ? toggleFolder(item.path) : null"
      >
        <!-- 目录折叠指示符 -->
        <span v-if="item.isDir" class="chevron" :data-test="`chevron-${item.path}`">
          {{ isCollapsed(item.path) ? '▸' : '▾' }}
        </span>
        <span v-else class="chevron-placeholder" />

        <!-- 节点图标 -->
        <i
          class="node-icon"
          :class="
            item.isDir
              ? (isCollapsed(item.path) ? 'icon-close-folder' : 'icon-open-folder')
              : 'icon-file'
          "
        />

        <!-- 文件或文件夹名称 -->
        <span class="node-name" :title="item.path">{{ item.name }}</span>

        <!-- 文件后操作按钮组：仅图标，无文字 -->
        <div v-if="!item.isDir" class="actions" @click.stop>
          <button
            class="action-btn preview-btn"
            title="预览"
            :data-test="`preview-btn-${item.path}`"
            @click.stop="handlePreview(item.path)"
          >
            <i class="icon-preview" />
          </button>
          <a
            class="action-btn download-btn"
            title="下载"
            :data-test="`download-btn-${item.path}`"
            :href="getDownloadUrl(item.path)"
            :download="item.name"
            @click.stop
          >
            <i class="icon-download" />
          </a>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useSessionStore } from '@/store/session'

export interface FileEntry {
  path: string
  isDir: boolean
}

export interface TreeNode {
  name: string
  path: string
  isDir: boolean
  children: TreeNode[]
}

export interface FlatNode {
  name: string
  path: string
  isDir: boolean
  depth: number
  hasChildren: boolean
}

const props = defineProps<{ taskId: string | null }>()
const session = useSessionStore()

const files = ref<FileEntry[]>([])
const collapsedPaths = ref<Set<string>>(new Set())

function isCollapsed(path: string): boolean {
  return collapsedPaths.value.has(path)
}

function toggleFolder(path: string): void {
  if (collapsedPaths.value.has(path)) {
    collapsedPaths.value.delete(path)
  } else {
    collapsedPaths.value.add(path)
  }
}

/**
 * 将平铺的文件路径解析成树形结构并进行排序（文件夹置顶、同级字母排序）
 */
function buildTree(entries: FileEntry[]): TreeNode[] {
  const root: TreeNode = { name: '', path: '', isDir: true, children: [] }

  for (const entry of entries) {
    const cleanPath = entry.path.replace(/^\/+|\/+$/g, '')
    if (!cleanPath) continue

    const parts = cleanPath.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1
      const subPath = parts.slice(0, i + 1).join('/')
      const isDir = isLast ? entry.isDir : true

      let child = current.children.find((c) => c.name === part)
      if (!child) {
        child = {
          name: part,
          path: subPath,
          isDir,
          children: [],
        }
        current.children.push(child)
      } else if (isLast && entry.isDir) {
        child.isDir = true
      }
      current = child
    }
  }

  function sortNodes(nodes: TreeNode[]): TreeNode[] {
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) {
        return a.isDir ? -1 : 1
      }
      return a.name.localeCompare(b.name, 'zh-CN')
    })
    for (const node of nodes) {
      if (node.children.length > 0) {
        sortNodes(node.children)
      }
    }
    return nodes
  }

  return sortNodes(root.children)
}

/**
 * 根据折叠状态计算当前可见的扁平列表
 */
const visibleNodes = computed<FlatNode[]>(() => {
  const tree = buildTree(files.value)
  const result: FlatNode[] = []

  function traverse(nodes: TreeNode[], depth: number) {
    for (const node of nodes) {
      result.push({
        name: node.name,
        path: node.path,
        isDir: node.isDir,
        depth,
        hasChildren: node.isDir && node.children.length > 0,
      })
      if (node.isDir && !collapsedPaths.value.has(node.path)) {
        traverse(node.children, depth + 1)
      }
    }
  }

  traverse(tree, 0)
  return result
})

function getDownloadUrl(path: string): string {
  if (!props.taskId) return '#'
  return `/api/tasks/${encodeURIComponent(props.taskId)}/artifacts/preview/${path}`
}

function handlePreview(path: string): void {
  if (!props.taskId) return
  const isMarkdown = path.toLowerCase().endsWith('.md') || path.toLowerCase().endsWith('.markdown')
  let previewUrl: string
  if (isMarkdown) {
    const params = new URLSearchParams({
      view: 'artifact',
      taskId: props.taskId,
      filePath: path,
      type: 'markdown',
    })
    previewUrl = `/?${params.toString()}`
  } else {
    previewUrl = `/api/tasks/${encodeURIComponent(props.taskId)}/artifacts/preview/${path}`
  }
  window.open(previewUrl, '_blank')
}

async function loadFiles(): Promise<void> {
  if (!props.taskId) {
    files.value = []
    return
  }
  try {
    const response = await fetch(`/api/tasks/${props.taskId}/files`)
    if (!response.ok) throw new Error(String(response.status))
    const body = await response.json()
    files.value = body.files ?? []
  } catch {
    files.value = []
  }
}

onMounted(loadFiles)
watch(() => props.taskId, loadFiles)
watch(() => session.artifacts.length, loadFiles)
watch(
  () => session.isStreaming,
  (streaming, prev) => {
    if (prev && !streaming) {
      loadFiles()
    }
  },
)
</script>

<style scoped>
.file-tree {
  height: 100%;
  overflow-y: auto;
  padding: 8px 4px;
}

.tree-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 12px;
  user-select: none;
  min-height: 28px;
  transition: background-color 0.15s ease;
}

.tree-item.is-dir {
  cursor: pointer;
  color: #1d2129;
  font-weight: 500;
}

.tree-item.is-dir:hover {
  background: var(--color-bg-subtle, #f2f3f5);
}

.tree-item.is-file {
  color: #4e5969;
}

.tree-item.is-file:hover {
  background: var(--color-bg-subtle, #f2f3f5);
}

.chevron {
  display: inline-block;
  width: 14px;
  text-align: center;
  font-size: 11px;
  color: #86909c;
  flex-shrink: 0;
}

.chevron-placeholder {
  display: inline-block;
  width: 14px;
  flex-shrink: 0;
}

.node-icon {
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-open-folder,
.icon-close-folder {
  color: #ffb400;
}

.icon-file {
  color: #165dff;
}

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  flex-shrink: 0;
  opacity: 0.7;
}

.tree-item:hover .actions {
  opacity: 1;
}

.action-btn {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: #4e5969;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.15s ease;
  font-size: 12px;
  padding: 0;
}

.action-btn:hover {
  color: #165dff;
  background: rgba(22, 93, 255, 0.1);
}

.empty {
  text-align: center;
  color: var(--color-text-muted, #86909c);
  font-size: 12px;
  margin-top: 32px;
}
</style>