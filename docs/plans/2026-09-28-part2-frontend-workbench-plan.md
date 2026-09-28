# Part 2: 前端三栏工作台 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Vue 3 + TypeScript + Vite 搭建 MateChat「左-中-右」三栏智能工作台，包含工作区/任务树侧栏、对话流主区、产物预览/Diff/文件/下载右栏，并通过 Mock SSE 与后端契约解耦。

**Architecture:** Pinia 管理三块状态（工作区树、当前会话、设置），API 层封装 fetch 与 SSE 解析，`src/mock/sse-server.ts` 提供与后端契约一致的事件流使 UI 可独立开发。三栏用 `splitpanes` 实现拖拽与折叠。中栏对话用 MateChat 组件，左右两栏自研。

**Tech Stack:** Vue 3.5、TypeScript 5、Vite 5、`@matechat/core`、`vue-devui`、`@devui-design/icons`、`splitpanes`、Pinia、`markdown-it`、`highlight.js`、`vue-diff`、Vitest、`@vue/test-utils`。

**前置条件**：Node v24.18.0、npm 11.16.0 已装（已实测）。

**契约来源**：SSE 事件格式以 [`Part 1 Task 10`](2026-09-28-part1-backend-agent-plan.md) 的 `server/service/events.py` 为唯一事实来源，前端 `src/api/events.ts` 必须逐字对齐。

---

## Task 1: Vite 工程初始化

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/styles/global.css`

- [ ] **Step 1: 用 Vite 脚手架生成工程**

```bash
cd /media/data/git/s_agent
npm create vite@latest frontend -- --template vue-ts
```

Expected: 生成 `frontend/` 目录，含 `package.json`、`vite.config.ts`、`src/`。

- [ ] **Step 2: 安装依赖**

```bash
cd /media/data/git/s_agent/frontend
npm install
npm install @matechat/core vue-devui @devui-design/icons
npm install splitpanes pinia markdown-it highlight.js vue-diff
npm install -D vitest @vue/test-utils jsdom @types/markdown-it
```

Expected: `node_modules/` 生成，`package.json` 中 dependencies 出现上述包。

> 若 `@matechat/core` 安装失败，运行 `npm view @matechat/core versions` 确认包名与可用版本，再重试。

- [ ] **Step 3: 写 `vite.config.ts`（含后端代理与测试配置）**

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Point this at the FastAPI backend to switch off the mock layer.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
  },
})
```

- [ ] **Step 4: 写 `src/styles/global.css`**

```css
:root {
  --sidebar-left-width: 260px;
  --sidebar-right-width: 380px;
  --topbar-height: 48px;
  --color-border: #e5e6eb;
  --color-bg-subtle: #f7f8fa;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}

body {
  color: #1d2129;
}
```

- [ ] **Step 5: 写 `src/main.ts`**

```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import MateChat from '@matechat/core'
import 'vue-devui/style.css'
import '@devui-design/icons/icomoon/devui-icon.css'
import 'splitpanes/dist/splitpanes.css'
import 'highlight.js/styles/github.css'
import '@/styles/global.css'

import App from './App.vue'

const app = createApp(App)

app.use(createPinia())
app.use(MateChat)

app.mount('#app')
```

- [ ] **Step 6: 写最小 `src/App.vue`（占位，Task 6 替换为三栏布局）**

```vue
<template>
  <div class="app-root">
    <h1>s_agent Workbench</h1>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.app-root {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```

- [ ] **Step 7: 写 `index.html`**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>s_agent 工作台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 8: 加测试脚本到 `package.json`**

在 `"scripts"` 中追加：

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 9: 启动开发服务器验证**

Run:
```bash
cd /media/data/git/s_agent/frontend
npm run dev
```
Expected: 终端输出 `Local: http://localhost:5173/`，浏览器打开显示 "s_agent Workbench"。验证后 `Ctrl+C` 停止。

- [ ] **Step 10: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
        frontend/tsconfig.json frontend/index.html frontend/src/main.ts \
        frontend/src/App.vue frontend/src/styles/global.css frontend/.gitignore
git commit -m "feat: frontend: scaffold Vite + Vue3 + MateChat project"
```

---

## Task 2: SSE 事件契约（前端侧）

**Files:**
- Create: `frontend/src/api/events.ts`
- Create: `frontend/tests/api/events.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/api/events.spec.ts`**

```ts
import { describe, expect, it } from 'vitest'
import {
  EVENT_NAMES,
  parseSseFrame,
  splitSseBuffer,
} from '@/api/events'

describe('SSE contract', () => {
  it('lists exactly the events the backend can emit', () => {
    // Mirrors server/service/events.py::EVENT_NAMES. A drift here means
    // the UI silently ignores frames it should render.
    expect([...EVENT_NAMES].sort()).toEqual(
      [
        'artifact_created',
        'done',
        'require_confirm',
        'text_delta',
        'thinking_delta',
        'tool_call_end',
        'tool_call_start',
      ].sort(),
    )
  })

  it('parses a text_delta frame', () => {
    const frame = 'event: text_delta\ndata: {"text":"你好"}\n\n'
    expect(parseSseFrame(frame)).toEqual({
      event: 'text_delta',
      data: { text: '你好' },
    })
  })

  it('parses a tool_call_start frame', () => {
    const frame =
      'event: tool_call_start\ndata: {"call_id":"c1","tool":"calculate","args":{"expression":"1+1"}}\n\n'
    const parsed = parseSseFrame(frame)
    expect(parsed.event).toBe('tool_call_start')
    expect(parsed.data.tool).toBe('calculate')
  })

  it('returns null for an unknown event name', () => {
    // Forward compatibility: a newer backend must not crash the UI.
    const frame = 'event: future_event\ndata: {"x":1}\n\n'
    expect(parseSseFrame(frame)).toBeNull()
  })

  it('returns null for a malformed frame', () => {
    expect(parseSseFrame('event: text_delta\n')).toBeNull()
    expect(parseSseFrame('garbage')).toBeNull()
  })

  it('splits a buffer into complete frames and a remainder', () => {
    const buffer =
      'event: text_delta\ndata: {"text":"a"}\n\n' +
      'event: text_delta\ndata: {"text":"b"}\n\n' +
      'event: text_de'
    const { frames, rest } = splitSseBuffer(buffer)
    expect(frames).toHaveLength(2)
    expect(rest).toBe('event: text_de')
  })

  it('leaves an incomplete buffer untouched', () => {
    const { frames, rest } = splitSseBuffer('event: text_delta\ndata: {"text":"a"}')
    expect(frames).toHaveLength(0)
    expect(rest).toContain('text_delta')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/api/events`

- [ ] **Step 3: 写实现 `frontend/src/api/events.ts`**

```ts
/**
 * The SSE wire contract, mirroring `server/service/events.py`.
 *
 * The two files must change together: this is a cross-language boundary
 * that TypeScript cannot check for us, so the event-name list is
 * duplicated deliberately and pinned by a test on each side.
 */

export const EVENT_NAMES = [
  'thinking_delta',
  'text_delta',
  'tool_call_start',
  'tool_call_end',
  'artifact_created',
  'require_confirm',
  'done',
] as const

export type EventName = (typeof EVENT_NAMES)[number]

export interface ThinkingDeltaData {
  text: string
}

export interface TextDeltaData {
  text: string
}

export interface ToolCallStartData {
  call_id: string
  tool: string
  args: Record<string, unknown>
}

export interface ToolCallEndData {
  call_id: string
  status: 'success' | 'error'
  result_summary: string
}

export interface ArtifactCreatedData {
  type: 'html' | 'markdown' | 'image' | 'text'
  file_path: string
  url: string
}

export interface RequireConfirmData {
  reply_id: string
  command: string
  reason: string
  action: 'allow'
}

export interface DoneData {
  task_status: string
}

export interface ParsedFrame {
  event: EventName
  data: Record<string, unknown>
}

const KNOWN = new Set<string>(EVENT_NAMES)

/**
 * Parse one complete SSE frame.
 *
 * @param frame - A frame terminated by a blank line.
 * @returns The parsed event, or `null` when the frame is malformed or
 *          carries an event name this client does not know about. Unknown
 *          names return null rather than throwing so a newer backend does
 *          not break an older UI.
 */
export function parseSseFrame(frame: string): ParsedFrame | null {
  const lines = frame.split('\n').filter((line) => line.length > 0)
  const eventLine = lines.find((line) => line.startsWith('event: '))
  const dataLine = lines.find((line) => line.startsWith('data: '))

  if (!eventLine || !dataLine) return null

  const event = eventLine.slice('event: '.length).trim()
  if (!KNOWN.has(event)) return null

  try {
    return {
      event: event as EventName,
      data: JSON.parse(dataLine.slice('data: '.length)),
    }
  } catch {
    return null
  }
}

/**
 * Split a streaming buffer into complete frames plus the trailing partial.
 *
 * SSE frames are delimited by a blank line. Chunks from the network arrive
 * at arbitrary boundaries, so a frame can be cut in half mid-JSON — the
 * remainder must be carried over to the next chunk rather than parsed.
 *
 * @param buffer - The accumulated raw text.
 * @returns The complete frames and the unconsumed remainder.
 */
export function splitSseBuffer(buffer: string): {
  frames: string[]
  rest: string
} {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  return { frames: parts.filter((part) => part.trim().length > 0), rest }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/api/events.ts frontend/tests/api/events.spec.ts
git commit -m "feat: frontend: mirror the backend SSE contract"
```

---

## Task 3: 类型定义与 API 客户端

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/tests/api/client.spec.ts`

- [ ] **Step 1: 写 `frontend/src/types/index.ts`**

```ts
/** Shared domain types for the workbench UI. */

export type TaskStatus = 'running' | 'completed' | 'suspended' | 'failed'

export interface Task {
  id: string
  title: string
  workspaceId: string
  status: TaskStatus
  updatedAt: string
  hasArtifacts: boolean
}

export interface Workspace {
  id: string
  name: string
  tasks: Task[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  /** Visible answer text. */
  text: string
  /** The model's reasoning, rendered in a collapsed block. */
  thinking: string
  /** Tool invocations in this turn, in order. */
  toolCalls: ToolCallRecord[]
  /** Set while the turn is still streaming. */
  streaming: boolean
}

export interface ToolCallRecord {
  callId: string
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'success' | 'error'
  summary: string
}

export interface PendingConfirm {
  replyId: string
  command: string
  reason: string
}

export interface Artifact {
  type: 'html' | 'markdown' | 'image' | 'text'
  filePath: string
  url: string
}

export interface ModelSettings {
  modelName: string
  baseUrl: string
}
```

- [ ] **Step 2: 写失败的测试 `frontend/tests/api/client.spec.ts`**

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiClient, ApiError } from '@/api/client'

describe('ApiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      }),
    )
    const client = new ApiClient('')
    expect(await client.get('/api/health')).toEqual({ status: 'ok' })
  })

  it('throws ApiError carrying the status code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'not found',
      }),
    )
    const client = new ApiClient('')
    await expect(client.get('/api/nope')).rejects.toBeInstanceOf(ApiError)
  })

  it('prefixes the base URL onto paths', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)
    const client = new ApiClient('http://api.test')
    await client.get('/api/health')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/health',
      expect.anything(),
    )
  })
})
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/api/client`

- [ ] **Step 4: 写实现 `frontend/src/api/client.ts`**

```ts
/**
 * Thin fetch wrapper for the backend REST API.
 *
 * A dedicated error type matters here: the workbench shows the user why a
 * pane is empty, and "request failed" is not an answer. Carrying the
 * status code lets callers distinguish "this task has no artifacts yet"
 * (404) from "the backend is down" (network error).
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class ApiClient {
  constructor(private readonly baseUrl: string = '') {}

  private url(path: string): string {
    return `${this.baseUrl}${path}`
  }

  async get<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path), {
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  /**
   * POST a message and consume the response as a stream of parsed SSE frames.
   *
   * @param path - The endpoint path.
   * @param body - The JSON request body.
   * @returns An async generator yielding parsed frames in arrival order.
   */
  async *stream(
    path: string,
    body: unknown,
  ): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
    const { parseSseFrame, splitSseBuffer } = await import('./events')

    const response = await fetch(this.url(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
    })

    if (!response.ok || !response.body) {
      throw new ApiError(await response.text(), response.status)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const { frames, rest } = splitSseBuffer(buffer)
      buffer = rest

      for (const frame of frames) {
        const parsed = parseSseFrame(frame)
        if (parsed) yield parsed
      }
    }
  }
}

export const apiClient = new ApiClient('')
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/tests/api/client.spec.ts
git commit -m "feat: frontend: add typed API client with SSE streaming"
```

---

## Task 4: Mock SSE 服务

**Files:**
- Create: `frontend/src/mock/sse-server.ts`
- Create: `frontend/tests/mock/sse-server.spec.ts`

- **背景**：Spec §5 要求前后端并行开发。本模块让前端在无后端时跑通全部交互。

- [ ] **Step 1: 写失败的测试 `frontend/tests/mock/sse-server.spec.ts`**

```ts
import { describe, expect, it } from 'vitest'
import { mockTurn } from '@/mock/sse-server'
import { parseSseFrame } from '@/api/events'

async function collect(message: string) {
  const frames: Array<{ event: string; data: Record<string, unknown> }> = []
  for await (const frame of mockTurn(message)) {
    const parsed = parseSseFrame(frame)
    if (parsed) frames.push(parsed)
  }
  return frames
}

describe('mockTurn', () => {
  it('emits a thinking chunk, text chunks, and a done event', async () => {
    const frames = await collect('你好')
    const names = frames.map((f) => f.event)
    expect(names).toContain('thinking_delta')
    expect(names).toContain('text_delta')
    expect(names[names.length - 1]).toBe('done')
  })

  it('echoes the user message in the reply', async () => {
    const frames = await collect('测试消息')
    const text = frames
      .filter((f) => f.event === 'text_delta')
      .map((f) => f.data.text as string)
      .join('')
    expect(text).toContain('测试消息')
  })

  it('emits a tool call pair for a shell-flavoured request', async () => {
    const frames = await collect('帮我执行 ls')
    const names = frames.map((f) => f.event)
    expect(names).toContain('tool_call_start')
    expect(names).toContain('tool_call_end')
  })

  it('emits an artifact event for a page request', async () => {
    const frames = await collect('帮我生成一个网页')
    expect(frames.map((f) => f.event)).toContain('artifact_created')
  })

  it('emits a confirm request for a dangerous command', async () => {
    const frames = await collect('删除所有文件')
    expect(frames.map((f) => f.event)).toContain('require_confirm')
  })

  it('produces only frames the real contract allows', async () => {
    // Every mock frame must survive the real parser, or the UI is being
    // developed against a contract the backend does not speak.
    for (const message of ['你好', '帮我执行 ls', '生成网页', '删除文件']) {
      for await (const frame of mockTurn(message)) {
        expect(parseSseFrame(frame)).not.toBeNull()
      }
    }
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/mock/sse-server`

- [ ] **Step 3: 写实现 `frontend/src/mock/sse-server.ts`**

```ts
/**
 * A local SSE simulator so the workbench can be built without the backend.
 *
 * Every frame this module emits is a real frame — the tests run them
 * through the production parser. That constraint is the point: a mock that
 * invents its own shapes would let the UI be built against a contract the
 * backend does not speak, and the gap would only surface at integration.
 *
 * It is deliberately keyword-driven so the common demo paths — a shell
 * command, a page generation, a destructive command — are all reachable
 * from the UI without a live model.
 */

const THINKING = '正在理解你的请求…'
const CHUNK_DELAY_MS = 60

function frame(event: string, payload: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Produce a simulated agent turn for a user message.
 *
 * @param message - The user's message, used to pick which events to emit.
 * @yields Raw SSE frames, in the same encoding the backend produces.
 */
export async function* mockTurn(message: string): AsyncGenerator<string> {
  const isDangerous = /删除|rm -rf|清空/.test(message)
  const isShell = /执行|shell|命令|ls|npm/.test(message)
  const isPage = /网页|页面|html|原型/.test(message)

  yield frame('thinking_delta', { text: THINKING })
  await sleep(CHUNK_DELAY_MS)

  // A destructive request pauses for human approval before doing anything.
  if (isDangerous) {
    yield frame('require_confirm', {
      reply_id: 'r-mock-1',
      command: 'rm -rf build',
      reason: '该命令会删除目录，属于高危操作',
      action: 'allow',
    })
    await sleep(CHUNK_DELAY_MS)
  }

  if (isShell) {
    yield frame('tool_call_start', {
      call_id: 'c-mock-1',
      tool: 'shell',
      args: { command: 'ls -la' },
    })
    await sleep(CHUNK_DELAY_MS)
    yield frame('tool_call_end', {
      call_id: 'c-mock-1',
      status: 'success',
      result_summary: 'total 12\ndrwxr-xr-x  src\n-rw-r--r--  package.json',
    })
    await sleep(CHUNK_DELAY_MS)
  }

  const reply = `收到你的请求：${message}。这是模拟回复，用于在未接入后端时调试界面。`
  for (const char of reply) {
    yield frame('text_delta', { text: char })
    await sleep(12)
  }

  if (isPage) {
    yield frame('artifact_created', {
      type: 'html',
      file_path: 'index.html',
      url: '/mock/artifacts/index.html',
    })
    await sleep(CHUNK_DELAY_MS)
  }

  yield frame('done', { task_status: 'completed' })
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/mock/sse-server.ts frontend/tests/mock/sse-server.spec.ts
git commit -m "feat: frontend: add contract-faithful mock SSE simulator"
```

---

## Task 5: 工作区与任务 Store

**Files:**
- Create: `frontend/src/store/workspaces.ts`
- Create: `frontend/tests/store/workspaces.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/store/workspaces.spec.ts`**

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from '@/store/workspaces'
import type { Workspace } from '@/types'

const FIXTURE: Workspace[] = [
  {
    id: 'w1',
    name: '项目 A',
    tasks: [
      {
        id: 't1',
        title: '生成落地页',
        workspaceId: 'w1',
        status: 'completed',
        updatedAt: '2026-09-28T10:00:00Z',
        hasArtifacts: true,
      },
      {
        id: 't2',
        title: '分析数据',
        workspaceId: 'w1',
        status: 'running',
        updatedAt: '2026-09-28T11:00:00Z',
        hasArtifacts: false,
      },
    ],
  },
  {
    id: 'w2',
    name: '项目 B',
    tasks: [
      {
        id: 't3',
        title: '写周报',
        workspaceId: 'w2',
        status: 'completed',
        updatedAt: '2026-09-27T09:00:00Z',
        hasArtifacts: false,
      },
    ],
  },
]

describe('workspace store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts empty', () => {
    const store = useWorkspaceStore()
    expect(store.workspaces).toEqual([])
  })

  it('loads workspaces', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    expect(store.workspaces).toHaveLength(2)
  })

  it('filters tasks across all workspaces by title', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.setSearchQuery('周报')
    expect(store.filteredWorkspaces).toHaveLength(1)
    expect(store.filteredWorkspaces[0].tasks).toHaveLength(1)
  })

  it('returns every workspace when the query is empty', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.setSearchQuery('')
    expect(store.filteredWorkspaces).toHaveLength(2)
  })

  it('search is case-insensitive', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.setSearchQuery('生成落地页')
    expect(store.filteredWorkspaces[0].tasks[0].id).toBe('t1')
  })

  it('selects a task', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.selectTask('t2')
    expect(store.activeTaskId).toBe('t2')
  })

  it('renames a task', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.renameTask('t1', '新标题')
    expect(store.findTask('t1')?.title).toBe('新标题')
  })

  it('archives a task by removing it from the tree', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.archiveTask('t1')
    expect(store.findTask('t1')).toBeUndefined()
  })

  it('clears a dangling active selection when its task is archived', () => {
    // Otherwise the chat pane keeps rendering a task the sidebar no longer
    // shows, and the user has no way back to a consistent state.
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    store.selectTask('t2')
    store.archiveTask('t2')
    expect(store.activeTaskId).toBeNull()
  })

  it('creates a task in the given workspace', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    const created = store.createTask('w2', '新任务')
    expect(created.title).toBe('新任务')
    expect(store.findTask(created.id)?.workspaceId).toBe('w2')
  })

  it('groups tasks under their workspace', () => {
    const store = useWorkspaceStore()
    store.setWorkspaces(FIXTURE)
    const workspace = store.filteredWorkspaces.find((w) => w.id === 'w1')
    expect(workspace?.tasks.map((t) => t.id)).toEqual(['t1', 't2'])
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/store/workspaces`

- [ ] **Step 3: 写实现 `frontend/src/store/workspaces.ts`**

```ts
/**
 * Workspace and task state for the left sidebar.
 *
 * Two invariants drive the design:
 *
 * 1. Search filters the *tree*, not a flat list — a workspace with no
 *    matching tasks disappears rather than rendering an empty group.
 * 2. Archiving the active task clears the selection. Leaving it set would
 *    strand the chat pane on a task the sidebar no longer shows.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Task, Workspace } from '@/types'

let taskCounter = 0

function newTaskId(): string {
  taskCounter += 1
  return `task-${Date.now()}-${taskCounter}`
}

export const useWorkspaceStore = defineStore('workspaces', () => {
  const workspaces = ref<Workspace[]>([])
  const searchQuery = ref('')
  const activeTaskId = ref<string | null>(null)

  /** Workspaces with their task lists filtered by the current query. */
  const filteredWorkspaces = computed<Workspace[]>(() => {
    const query = searchQuery.value.trim().toLowerCase()
    if (!query) return workspaces.value

    return workspaces.value
      .map((workspace) => ({
        ...workspace,
        tasks: workspace.tasks.filter((task) =>
          task.title.toLowerCase().includes(query),
        ),
      }))
      .filter((workspace) => workspace.tasks.length > 0)
  })

  const activeTask = computed<Task | null>(
    () => findTask(activeTaskId.value) ?? null,
  )

  function setWorkspaces(next: Workspace[]): void {
    workspaces.value = next
  }

  function setSearchQuery(query: string): void {
    searchQuery.value = query
  }

  function findTask(taskId: string | null): Task | undefined {
    if (!taskId) return undefined
    for (const workspace of workspaces.value) {
      const found = workspace.tasks.find((task) => task.id === taskId)
      if (found) return found
    }
    return undefined
  }

  function selectTask(taskId: string): void {
    activeTaskId.value = taskId
  }

  function renameTask(taskId: string, title: string): void {
    const trimmed = title.trim()
    if (!trimmed) return
    const task = findTask(taskId)
    if (task) {
      task.title = trimmed
      task.updatedAt = new Date().toISOString()
    }
  }

  function archiveTask(taskId: string): void {
    for (const workspace of workspaces.value) {
      const index = workspace.tasks.findIndex((task) => task.id === taskId)
      if (index >= 0) {
        workspace.tasks.splice(index, 1)
        break
      }
    }
    // Keep the selection consistent with the visible tree.
    if (activeTaskId.value === taskId) {
      activeTaskId.value = null
    }
  }

  function createTask(workspaceId: string, title: string): Task {
    const workspace = workspaces.value.find((item) => item.id === workspaceId)
    if (!workspace) {
      throw new Error(`Unknown workspace ${workspaceId}`)
    }

    const task: Task = {
      id: newTaskId(),
      title,
      workspaceId,
      status: 'running',
      updatedAt: new Date().toISOString(),
      hasArtifacts: false,
    }
    workspace.tasks.unshift(task)
    return task
  }

  function markArtifacts(taskId: string): void {
    const task = findTask(taskId)
    if (task) task.hasArtifacts = true
  }

  return {
    workspaces,
    searchQuery,
    activeTaskId,
    filteredWorkspaces,
    activeTask,
    setWorkspaces,
    setSearchQuery,
    findTask,
    selectTask,
    renameTask,
    archiveTask,
    createTask,
    markArtifacts,
  }
})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 27 passed

- [ ] **Step 5: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/store/workspaces.ts frontend/tests/store/workspaces.spec.ts
git commit -m "feat: frontend: add workspace and task store"
```

---

## Task 6: 会话 Store（消息流 + SSE 消费）

**Files:**
- Create: `frontend/src/store/session.ts`
- Create: `frontend/tests/store/session.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/store/session.spec.ts`**

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '@/store/session'
import type { ParsedFrame } from '@/api/events'

function frame(event: string, data: Record<string, unknown>): ParsedFrame {
  return { event: event as ParsedFrame['event'], data }
}

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with no messages', () => {
    const store = useSessionStore()
    expect(store.messages).toHaveLength(0)
  })

  it('appends a user message', () => {
    const store = useSessionStore()
    store.addUserMessage('你好')
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('user')
    expect(store.messages[0].text).toBe('你好')
  })

  it('creates an empty assistant message for the turn', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('assistant')
    expect(store.messages[0].streaming).toBe(true)
  })

  it('accumulates text deltas into the assistant message', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('text_delta', { text: '你' }))
    store.applyFrame(frame('text_delta', { text: '好' }))
    expect(store.messages[0].text).toBe('你好')
  })

  it('accumulates thinking deltas separately from answer text', () => {
    // Thinking must not leak into the answer: it is rendered collapsed and
    // a user reading the transcript should not see reasoning inline.
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('thinking_delta', { text: '想' }))
    store.applyFrame(frame('text_delta', { text: '答' }))
    expect(store.messages[0].thinking).toBe('想')
    expect(store.messages[0].text).toBe('答')
  })

  it('strips <think> tags the model inlines into answer text', () => {
    // v-flash emits reasoning wrapped in <think>…</think> inside the text
    // stream; verified against the live model on 2026-09-28.
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('text_delta', { text: '<think>推理中</think>正式回答' }))
    expect(store.messages[0].text).toBe('正式回答')
    expect(store.messages[0].thinking).toContain('推理中')
  })

  it('records a tool call and its completion', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(
      frame('tool_call_start', {
        call_id: 'c1',
        tool: 'calculate',
        args: { expression: '1+1' },
      }),
    )
    expect(store.messages[0].toolCalls).toHaveLength(1)
    expect(store.messages[0].toolCalls[0].status).toBe('running')

    store.applyFrame(
      frame('tool_call_end', {
        call_id: 'c1',
        status: 'success',
        result_summary: '2',
      }),
    )
    expect(store.messages[0].toolCalls[0].status).toBe('success')
    expect(store.messages[0].toolCalls[0].summary).toBe('2')
  })

  it('marks the turn finished on done', () => {
    const store = useSessionStore()
    store.beginAssistantTurn()
    store.applyFrame(frame('done', { task_status: 'completed' }))
    expect(store.messages[0].streaming).toBe(false)
  })

  it('records a pending confirmation request', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('require_confirm', {
        reply_id: 'r1',
        command: 'rm -rf build',
        reason: '高危',
        action: 'allow',
      }),
    )
    expect(store.pendingConfirm?.replyId).toBe('r1')
  })

  it('clears the pending confirmation once resolved', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('require_confirm', {
        reply_id: 'r1',
        command: 'rm -rf build',
        reason: '高危',
        action: 'allow',
      }),
    )
    store.resolveConfirm('allow')
    expect(store.pendingConfirm).toBeNull()
  })

  it('collects artifacts announced during the turn', () => {
    const store = useSessionStore()
    store.applyFrame(
      frame('artifact_created', {
        type: 'html',
        file_path: 'index.html',
        url: '/api/tasks/t1/artifacts/preview/index.html',
      }),
    )
    expect(store.artifacts).toHaveLength(1)
    expect(store.artifacts[0].filePath).toBe('index.html')
  })

  it('deduplicates artifacts by path', () => {
    const store = useSessionStore()
    const payload = {
      type: 'html',
      file_path: 'index.html',
      url: '/api/tasks/t1/artifacts/preview/index.html',
    }
    store.applyFrame(frame('artifact_created', payload))
    store.applyFrame(frame('artifact_created', payload))
    expect(store.artifacts).toHaveLength(1)
  })

  it('resets the session on task switch', () => {
    const store = useSessionStore()
    store.addUserMessage('旧消息')
    store.reset()
    expect(store.messages).toHaveLength(0)
    expect(store.artifacts).toHaveLength(0)
  })

  it('ignores any frame when no turn is open', () => {
    // Frames can arrive after a reset; applying them would corrupt state.
    const store = useSessionStore()
    store.applyFrame(frame('text_delta', { text: '孤儿' }))
    expect(store.messages).toHaveLength(0)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/store/session`

- [ ] **Step 3: 写实现 `frontend/src/store/session.ts`**

```ts
/**
 * The conversation state for the middle pane.
 *
 * Two pieces of real-world handling live here rather than in components:
 *
 * 1. `<think>` unwrapping. The `v-flash` model streams its reasoning
 *    wrapped in `<think>…</think>` inside the text channel (verified
 *    against the live model on 2026-09-28). Leaving those tags in the
 *    transcript would show raw markup to the user.
 * 2. Turn guarding. Frames are ignored unless a turn is open, so a straggler
 *    arriving after a reset cannot repopulate a cleared conversation.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ParsedFrame } from '@/api/events'
import type { Artifact, ChatMessage, PendingConfirm } from '@/types'

let messageCounter = 0

function newMessageId(): string {
  messageCounter += 1
  return `msg-${Date.now()}-${messageCounter}`
}

const THINK_OPEN = '<think>'
const THINK_CLOSE = '</think>'

export const useSessionStore = defineStore('session', () => {
  const messages = ref<ChatMessage[]>([])
  const artifacts = ref<Artifact[]>([])
  const pendingConfirm = ref<PendingConfirm | null>(null)
  const turnOpen = ref(false)

  /** The assistant message currently being streamed, if any. */
  const currentAssistant = computed<ChatMessage | null>(() => {
    const last = messages.value[messages.value.length - 1]
    return last && last.role === 'assistant' && last.streaming ? last : null
  })

  const isStreaming = computed(() => turnOpen.value)

  function addUserMessage(text: string): void {
    messages.value.push({
      id: newMessageId(),
      role: 'user',
      text,
      thinking: '',
      toolCalls: [],
      streaming: false,
    })
  }

  function beginAssistantTurn(): void {
    messages.value.push({
      id: newMessageId(),
      role: 'assistant',
      text: '',
      thinking: '',
      toolCalls: [],
      streaming: true,
    })
    turnOpen.value = true
  }

  /**
   * Append raw model text, unwrapping any `<think>` block it contains.
   *
   * @param message - The assistant message to append to.
   * @param chunk - The raw chunk, which may contain thinking tags.
   */
  function appendText(message: ChatMessage, chunk: string): void {
    let remaining = chunk

    // A complete think block inside a single chunk.
    while (remaining.includes(THINK_OPEN)) {
      const openIndex = remaining.indexOf(THINK_OPEN)
      const before = remaining.slice(0, openIndex)
      const afterOpen = remaining.slice(openIndex + THINK_OPEN.length)
      const closeIndex = afterOpen.indexOf(THINK_CLOSE)

      if (closeIndex === -1) {
        // The block is still streaming: hold everything after the opening
        // tag in the thinking buffer until the closing tag arrives.
        message.thinking += afterOpen
        message.text += before
        return
      }

      message.thinking += afterOpen.slice(0, closeIndex)
      message.text += before
      remaining = afterOpen.slice(closeIndex + THINK_CLOSE.length)
    }

    message.text += remaining
  }

  function applyFrame(parsed: ParsedFrame): void {
    switch (parsed.event) {
      case 'thinking_delta': {
        const message = currentAssistant.value
        if (!message) return
        message.thinking += String(parsed.data.text ?? '')
        return
      }

      case 'text_delta': {
        const message = currentAssistant.value
        if (!message) return
        appendText(message, String(parsed.data.text ?? ''))
        return
      }

      case 'tool_call_start': {
        const message = currentAssistant.value
        if (!message) return
        message.toolCalls.push({
          callId: String(parsed.data.call_id ?? ''),
          tool: String(parsed.data.tool ?? ''),
          args: (parsed.data.args as Record<string, unknown>) ?? {},
          status: 'running',
          summary: '',
        })
        return
      }

      case 'tool_call_end': {
        const message = currentAssistant.value
        if (!message) return
        const callId = String(parsed.data.call_id ?? '')
        const record = message.toolCalls.find((call) => call.callId === callId)
        if (record) {
          record.status = parsed.data.status === 'error' ? 'error' : 'success'
          record.summary = String(parsed.data.result_summary ?? '')
        }
        return
      }

      case 'artifact_created': {
        const filePath = String(parsed.data.file_path ?? '')
        // A task may regenerate the same file; the pane shows one entry.
        if (artifacts.value.some((item) => item.filePath === filePath)) return
        artifacts.value.push({
          type: (parsed.data.type as Artifact['type']) ?? 'text',
          filePath,
          url: String(parsed.data.url ?? ''),
        })
        return
      }

      case 'require_confirm': {
        pendingConfirm.value = {
          replyId: String(parsed.data.reply_id ?? ''),
          command: String(parsed.data.command ?? ''),
          reason: String(parsed.data.reason ?? ''),
        }
        return
      }

      case 'done': {
        const message = currentAssistant.value
        if (message) message.streaming = false
        turnOpen.value = false
        return
      }

      default:
        return
    }
  }

  function resolveConfirm(_action: 'allow' | 'deny'): void {
    pendingConfirm.value = null
  }

  function reset(): void {
    messages.value = []
    artifacts.value = []
    pendingConfirm.value = null
    turnOpen.value = false
  }

  return {
    messages,
    artifacts,
    pendingConfirm,
    isStreaming,
    currentAssistant,
    addUserMessage,
    beginAssistantTurn,
    applyFrame,
    resolveConfirm,
    reset,
  }
})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 41 passed

- [ ] **Step 5: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/store/session.ts frontend/tests/store/session.spec.ts
git commit -m "feat: frontend: add session store with SSE frame handling"
```

---

## Task 7: 设置 Store 与设置抽屉

**Files:**
- Create: `frontend/src/store/settings.ts`
- Create: `frontend/src/components/sidebar/SettingsDrawer.vue`
- Create: `frontend/tests/store/settings.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/store/settings.spec.ts`**

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '@/store/settings'

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('defaults to the locally verified model', () => {
    const store = useSettingsStore()
    expect(store.modelName).toBe('v-flash')
    expect(store.baseUrl).toBe('http://127.0.0.1:4000/v1')
  })

  it('defaults to confirming only high-risk actions', () => {
    const store = useSettingsStore()
    expect(store.hitlMode).toBe('dangerous')
  })

  it('updates the model', () => {
    const store = useSettingsStore()
    store.setModel('other-model')
    expect(store.modelName).toBe('other-model')
  })

  it('cycles through HITL modes', () => {
    const store = useSettingsStore()
    store.setHitlMode('always')
    expect(store.hitlMode).toBe('always')
    store.setHitlMode('never')
    expect(store.hitlMode).toBe('never')
  })

  it('opens and closes the drawer', () => {
    const store = useSettingsStore()
    expect(store.drawerOpen).toBe(false)
    store.openDrawer()
    expect(store.drawerOpen).toBe(true)
    store.closeDrawer()
    expect(store.drawerOpen).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/store/settings`

- [ ] **Step 3: 写实现 `frontend/src/store/settings.ts`**

```ts
/**
 * User settings backing the settings drawer.
 *
 * Defaults mirror the values verified against the local deployment on
 * 2026-09-28, so a fresh install works without configuration.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type HitlMode = 'always' | 'dangerous' | 'never'

export const useSettingsStore = defineStore('settings', () => {
  const modelName = ref('v-flash')
  const baseUrl = ref('http://127.0.0.1:4000/v1')
  const hitlMode = ref<HitlMode>('dangerous')
  const drawerOpen = ref(false)

  function setModel(name: string): void {
    modelName.value = name
  }

  function setBaseUrl(url: string): void {
    baseUrl.value = url
  }

  function setHitlMode(mode: HitlMode): void {
    hitlMode.value = mode
  }

  function openDrawer(): void {
    drawerOpen.value = true
  }

  function closeDrawer(): void {
    drawerOpen.value = false
  }

  return {
    modelName,
    baseUrl,
    hitlMode,
    drawerOpen,
    setModel,
    setBaseUrl,
    setHitlMode,
    openDrawer,
    closeDrawer,
  }
})
```

- [ ] **Step 4: 写 `frontend/src/components/sidebar/SettingsDrawer.vue`**

```vue
<template>
  <div v-if="settings.drawerOpen" class="drawer-backdrop" @click.self="settings.closeDrawer()">
    <aside class="drawer" role="dialog" aria-label="设置">
      <header class="drawer-header">
        <h2>设置</h2>
        <button class="icon-button" aria-label="关闭" @click="settings.closeDrawer()">✕</button>
      </header>

      <section class="drawer-section">
        <label class="field">
          <span class="field-label">模型</span>
          <input v-model="modelInput" class="field-input" />
        </label>

        <label class="field">
          <span class="field-label">API 端点</span>
          <input v-model="baseUrlInput" class="field-input" />
        </label>
      </section>

      <section class="drawer-section">
        <span class="field-label">权限确认</span>
        <div class="radio-group">
          <label v-for="option in hitlOptions" :key="option.value" class="radio">
            <input
              type="radio"
              :value="option.value"
              :checked="settings.hitlMode === option.value"
              @change="settings.setHitlMode(option.value)"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
      </section>

      <footer class="drawer-footer">
        <span class="hint">修改在下次对话时生效</span>
      </footer>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useSettingsStore, type HitlMode } from '@/store/settings'

const settings = useSettingsStore()

const modelInput = ref(settings.modelName)
const baseUrlInput = ref(settings.baseUrl)

// Keep the local buffers in step when the store changes from elsewhere.
watch(() => settings.modelName, (value) => (modelInput.value = value))
watch(() => settings.baseUrl, (value) => (baseUrlInput.value = value))

watch(modelInput, (value) => settings.setModel(value))
watch(baseUrlInput, (value) => settings.setBaseUrl(value))

const hitlOptions: Array<{ value: HitlMode; label: string }> = [
  { value: 'always', label: '每次操作都确认' },
  { value: 'dangerous', label: '仅高危操作确认' },
  { value: 'never', label: '自动放行' },
]
</script>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: flex-start;
  z-index: 1000;
}

.drawer {
  width: 360px;
  height: 100%;
  background: #fff;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 20px;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.drawer-header h2 {
  font-size: 16px;
  margin: 0;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  color: #4e5969;
}

.field-input {
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.drawer-footer {
  margin-top: auto;
}

.hint {
  font-size: 12px;
  color: #86909c;
}

.icon-button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
}
</style>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 46 passed

- [ ] **Step 6: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/store/settings.ts frontend/src/components/sidebar/SettingsDrawer.vue \
        frontend/tests/store/settings.spec.ts
git commit -m "feat: frontend: add settings store and drawer"
```

---

## Task 8: 左栏 — 工作区树与搜索

**Files:**
- Create: `frontend/src/components/sidebar/WorkspaceTree.vue`
- Create: `frontend/src/components/sidebar/SidebarLeft.vue`
- Create: `frontend/tests/components/WorkspaceTree.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/components/WorkspaceTree.spec.ts`**

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkspaceTree from '@/components/sidebar/WorkspaceTree.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import type { Workspace } from '@/types'

const FIXTURE: Workspace[] = [
  {
    id: 'w1',
    name: '项目 A',
    tasks: [
      {
        id: 't1',
        title: '生成落地页',
        workspaceId: 'w1',
        status: 'completed',
        updatedAt: '2026-09-28T10:00:00Z',
        hasArtifacts: true,
      },
    ],
  },
]

function mountTree() {
  setActivePinia(createPinia())
  const store = useWorkspaceStore()
  store.setWorkspaces(JSON.parse(JSON.stringify(FIXTURE)))
  return { wrapper: mount(WorkspaceTree), store }
}

describe('WorkspaceTree', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders each workspace as a group', () => {
    const { wrapper } = mountTree()
    expect(wrapper.text()).toContain('项目 A')
  })

  it('renders the tasks inside a group', () => {
    const { wrapper } = mountTree()
    expect(wrapper.text()).toContain('生成落地页')
  })

  it('selects a task on click', async () => {
    const { wrapper, store } = mountTree()
    await wrapper.find('[data-test="task-t1"]').trigger('click')
    expect(store.activeTaskId).toBe('t1')
  })

  it('shows no tasks when the search excludes them', async () => {
    const { wrapper, store } = mountTree()
    store.setSearchQuery('不存在的内容')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('生成落地页')
  })

  it('marks the active task', async () => {
    const { wrapper, store } = mountTree()
    store.selectTask('t1')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="task-t1"]').classes()).toContain('active')
  })

  it('shows an artifact badge when the task has artifacts', () => {
    const { wrapper } = mountTree()
    expect(wrapper.find('[data-test="artifact-badge-t1"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `WorkspaceTree.vue`

- [ ] **Step 3: 写实现 `frontend/src/components/sidebar/WorkspaceTree.vue`**

```vue
<template>
  <div class="workspace-tree">
    <section
      v-for="workspace in store.filteredWorkspaces"
      :key="workspace.id"
      class="workspace-group"
    >
      <header class="group-header" @click="toggle(workspace.id)">
        <span class="chevron">{{ isCollapsed(workspace.id) ? '▸' : '▾' }}</span>
        <span class="group-name">{{ workspace.name }}</span>
        <span class="group-count">{{ workspace.tasks.length }}</span>
      </header>

      <ul v-show="!isCollapsed(workspace.id)" class="task-list">
        <li
          v-for="task in workspace.tasks"
          :key="task.id"
          class="task-item"
          :class="[`status-${task.status}`, { active: task.id === store.activeTaskId }]"
          :data-test="`task-${task.id}`"
          @click="store.selectTask(task.id)"
        >
          <span class="status-dot" :title="task.status" />
          <span class="task-title">{{ task.title }}</span>
          <span
            v-if="task.hasArtifacts"
            class="artifact-badge"
            :data-test="`artifact-badge-${task.id}`"
            title="有产物"
            >◈</span
          >
        </li>
      </ul>
    </section>

    <p v-if="store.filteredWorkspaces.length === 0" class="empty">
      没有匹配的任务
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspaceStore } from '@/store/workspaces'

const store = useWorkspaceStore()
const collapsed = ref<Set<string>>(new Set())

function isCollapsed(workspaceId: string): boolean {
  return collapsed.value.has(workspaceId)
}

function toggle(workspaceId: string): void {
  const next = new Set(collapsed.value)
  if (next.has(workspaceId)) {
    next.delete(workspaceId)
  } else {
    next.add(workspaceId)
  }
  collapsed.value = next
}
</script>

<style scoped>
.workspace-tree {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  flex: 1;
  padding: 4px 0;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 12px;
  color: #86909c;
  text-transform: uppercase;
}

.group-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
}

.task-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px 7px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.task-item:hover {
  background: var(--color-bg-subtle);
}

.task-item.active {
  background: #e8f3ff;
  color: #165dff;
}

.task-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c9cdd4;
  flex-shrink: 0;
}

.status-running .status-dot {
  background: #165dff;
}

.status-completed .status-dot {
  background: #00b42a;
}

.status-failed .status-dot {
  background: #f53f3f;
}

.status-suspended .status-dot {
  background: #ff7d00;
}

.artifact-badge {
  font-size: 11px;
  color: #86909c;
}

.empty {
  font-size: 12px;
  color: #86909c;
  text-align: center;
  padding: 16px 0;
}
</style>
```

- [ ] **Step 4: 写实现 `frontend/src/components/sidebar/SidebarLeft.vue`**

```vue
<template>
  <aside class="sidebar-left">
    <header class="sidebar-header">
      <button class="new-task" @click="createTask">+ 新建任务</button>
      <input
        v-model="query"
        class="search-input"
        placeholder="搜索任务"
        type="search"
      />
    </header>

    <WorkspaceTree />

    <footer class="sidebar-footer">
      <button class="user-button" @click="settings.openDrawer()">
        <span class="avatar">A</span>
        <span class="user-name">用户</span>
        <span class="settings-icon">⚙</span>
      </button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import WorkspaceTree from './WorkspaceTree.vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSettingsStore } from '@/store/settings'

const store = useWorkspaceStore()
const settings = useSettingsStore()

const query = computed({
  get: () => store.searchQuery,
  set: (value: string) => store.setSearchQuery(value),
})

function createTask(): void {
  const target = store.workspaces[0]
  if (!target) return
  const task = store.createTask(target.id, '新任务')
  store.selectTask(task.id)
}
</script>

<style scoped>
.sidebar-left {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  background: #fff;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.new-task {
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.new-task:hover {
  background: var(--color-bg-subtle);
}

.search-input {
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
}

.sidebar-footer {
  border-top: 1px solid var(--color-border);
  padding: 8px;
}

.user-button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.user-button:hover {
  background: var(--color-bg-subtle);
}

.avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #165dff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.user-name {
  flex: 1;
  text-align: left;
}
</style>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 52 passed

- [ ] **Step 6: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/components/sidebar/WorkspaceTree.vue \
        frontend/src/components/sidebar/SidebarLeft.vue \
        frontend/tests/components/WorkspaceTree.spec.ts
git commit -m "feat: frontend: add left sidebar with workspace tree"
```

---

## Task 9: 中栏 — 对话流组件

**Files:**
- Create: `frontend/src/components/chat/UserMessage.vue`
- Create: `frontend/src/components/chat/ThinkingBlock.vue`
- Create: `frontend/src/components/chat/ToolCallCard.vue`
- Create: `frontend/src/components/chat/HitlConfirmCard.vue`
- Create: `frontend/src/components/chat/AssistantMessage.vue`
- Create: `frontend/src/components/chat/MessageList.vue`
- Create: `frontend/tests/components/MessageList.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/components/MessageList.spec.ts`**

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MessageList from '@/components/chat/MessageList.vue'
import { useSessionStore } from '@/store/session'

function mountList() {
  setActivePinia(createPinia())
  const store = useSessionStore()
  return { wrapper: mount(MessageList), store }
}

describe('MessageList', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders user messages', async () => {
    const { wrapper, store } = mountList()
    store.addUserMessage('帮我做件事')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('帮我做件事')
  })

  it('renders assistant text', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({ event: 'text_delta', data: { text: '好的' } } as never)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('好的')
  })

  it('renders a tool call card', async () => {
    const { wrapper, store } = mountList()
    store.beginAssistantTurn()
    store.applyFrame({
      event: 'tool_call_start',
      data: { call_id: 'c1', tool: 'calculate', args: {} },
    } as never)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('calculate')
  })

  it('renders the confirmation card when a confirm is pending', async () => {
    const { wrapper, store } = mountList()
    store.applyFrame({
      event: 'require_confirm',
      data: { reply_id: 'r1', command: 'rm -rf build', reason: '高危', action: 'allow' },
    } as never)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('rm -rf build')
  })

  it('shows an empty state before any message', () => {
    const { wrapper } = mountList()
    expect(wrapper.find('[data-test="empty-state"]').exists()).toBe(true)
  })

  it('hides the empty state once a message exists', async () => {
    const { wrapper, store } = mountList()
    store.addUserMessage('嗨')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="empty-state"]').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `MessageList.vue`

- [ ] **Step 3: 写 `frontend/src/components/chat/UserMessage.vue`**

```vue
<template>
  <div class="user-message">
    <div class="bubble">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<style scoped>
.user-message {
  display: flex;
  justify-content: flex-end;
  margin: 12px 0;
}

.bubble {
  max-width: 70%;
  padding: 10px 14px;
  background: #165dff;
  color: #fff;
  border-radius: 12px 12px 2px 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
```

- [ ] **Step 4: 写 `frontend/src/components/chat/ThinkingBlock.vue`**

```vue
<template>
  <div v-if="text" class="thinking-block">
    <button class="thinking-toggle" @click="expanded = !expanded">
      <span class="chevron">{{ expanded ? '▾' : '▸' }}</span>
      <span>思考过程</span>
      <span class="char-count">{{ text.length }} 字</span>
    </button>
    <pre v-show="expanded" class="thinking-text">{{ text }}</pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ text: string }>()

const expanded = ref(false)
</script>

<style scoped>
.thinking-block {
  margin: 8px 0;
  border-left: 2px solid #e5e6eb;
  padding-left: 10px;
}

.thinking-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: #86909c;
  padding: 2px 0;
}

.char-count {
  font-size: 11px;
  color: #c9cdd4;
}

.thinking-text {
  margin: 6px 0 0;
  font-size: 12px;
  color: #4e5969;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  max-height: 240px;
  overflow-y: auto;
}
</style>
```

- [ ] **Step 5: 写 `frontend/src/components/chat/ToolCallCard.vue`**

```vue
<template>
  <div class="tool-call" :class="`status-${call.status}`">
    <header class="tool-header">
      <span class="tool-icon">{{ statusIcon }}</span>
      <span class="tool-name">{{ call.tool }}</span>
      <span class="tool-status">{{ statusLabel }}</span>
    </header>
    <pre class="tool-args">{{ argsPreview }}</pre>
    <pre v-if="call.summary" class="tool-result">{{ call.summary }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ToolCallRecord } from '@/types'

const props = defineProps<{ call: ToolCallRecord }>()

const statusIcon = computed(() => {
  switch (props.call.status) {
    case 'running':
      return '◌'
    case 'success':
      return '✓'
    default:
      return '✕'
  }
})

const statusLabel = computed(() => {
  switch (props.call.status) {
    case 'running':
      return '执行中'
    case 'success':
      return '完成'
    default:
      return '失败'
  }
})

const argsPreview = computed(() => {
  const entries = Object.entries(props.call.args)
  if (entries.length === 0) return ''
  return entries.map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join('\n')
})
</script>

<style scoped>
.tool-call {
  margin: 8px 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--color-bg-subtle);
  font-size: 12px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-name {
  font-weight: 600;
  color: #1d2129;
}

.tool-status {
  margin-left: auto;
  color: #86909c;
}

.status-success .tool-icon {
  color: #00b42a;
}

.status-error .tool-icon {
  color: #f53f3f;
}

.status-running .tool-icon {
  color: #165dff;
}

.tool-args,
.tool-result {
  margin: 6px 0 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  color: #4e5969;
  max-height: 160px;
  overflow-y: auto;
}
</style>
```

- [ ] **Step 6: 写 `frontend/src/components/chat/HitlConfirmCard.vue`**

```vue
<template>
  <div class="hitl-card">
    <header class="hitl-header">
      <span class="hitl-icon">⚠</span>
      <span>需要你的确认</span>
    </header>
    <p class="hitl-reason">{{ confirm.reason }}</p>
    <pre class="hitl-command">{{ confirm.command }}</pre>
    <footer class="hitl-actions">
      <button class="btn btn-deny" @click="emit('deny')">拒绝</button>
      <button class="btn btn-allow" @click="emit('allow')">允许执行</button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import type { PendingConfirm } from '@/types'

defineProps<{ confirm: PendingConfirm }>()

const emit = defineEmits<{ allow: []; deny: [] }>()
</script>

<style scoped>
.hitl-card {
  margin: 12px 0;
  border: 1px solid #ff7d00;
  border-radius: 8px;
  padding: 12px;
  background: #fff7e8;
}

.hitl-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #d25f00;
}

.hitl-reason {
  margin: 8px 0 4px;
  font-size: 13px;
  color: #4e5969;
}

.hitl-command {
  margin: 0;
  padding: 8px;
  background: #fff;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.hitl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: #fff;
}

.btn-allow {
  background: #165dff;
  border-color: #165dff;
  color: #fff;
}

.btn-deny:hover {
  background: var(--color-bg-subtle);
}
</style>
```

- [ ] **Step 7: 写 `frontend/src/components/chat/AssistantMessage.vue`**

```vue
<template>
  <div class="assistant-message">
    <ThinkingBlock :text="message.thinking" />
    <ToolCallCard v-for="call in message.toolCalls" :key="call.callId" :call="call" />
    <div v-if="message.text" class="assistant-text" v-html="renderedText" />
    <span v-if="message.streaming" class="cursor" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
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
.assistant-message {
  margin: 12px 0;
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
```

- [ ] **Step 8: 写 `frontend/src/components/chat/MessageList.vue`**

```vue
<template>
  <div ref="scrollArea" class="message-list">
    <p v-if="store.messages.length === 0" data-test="empty-state" class="empty-state">
      描述你想完成的任务，Agent 会规划步骤并执行。
    </p>

    <template v-for="message in store.messages" :key="message.id">
      <UserMessage v-if="message.role === 'user'" :text="message.text" />
      <AssistantMessage v-else :message="message" />
    </template>

    <HitlConfirmCard
      v-if="store.pendingConfirm"
      :confirm="store.pendingConfirm"
      @allow="store.resolveConfirm('allow')"
      @deny="store.resolveConfirm('deny')"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import HitlConfirmCard from './HitlConfirmCard.vue'
import { useSessionStore } from '@/store/session'

const store = useSessionStore()
const scrollArea = ref<HTMLElement | null>(null)

// Follow the stream: without this the newest tokens render below the fold
// and the user has to chase the output with the scrollbar.
watch(
  () => [
    store.messages.length,
    store.messages[store.messages.length - 1]?.text,
    store.pendingConfirm,
  ],
  async () => {
    await nextTick()
    if (scrollArea.value) {
      scrollArea.value.scrollTop = scrollArea.value.scrollHeight
    }
  },
  { deep: true },
)
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.empty-state {
  text-align: center;
  color: #86909c;
  font-size: 13px;
  margin-top: 48px;
}
</style>
```

- [ ] **Step 9: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 58 passed

- [ ] **Step 10: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/components/chat/UserMessage.vue \
        frontend/src/components/chat/ThinkingBlock.vue \
        frontend/src/components/chat/ToolCallCard.vue \
        frontend/src/components/chat/HitlConfirmCard.vue \
        frontend/src/components/chat/AssistantMessage.vue \
        frontend/src/components/chat/MessageList.vue \
        frontend/tests/components/MessageList.spec.ts
git commit -m "feat: frontend: add chat message list with tool and HITL cards"
```

---

## Task 10: 中栏 — 输入框、任务标题与容器

**Files:**
- Create: `frontend/src/components/chat/ChatInput.vue`
- Create: `frontend/src/components/chat/TaskHeaderBar.vue`
- Create: `frontend/src/components/chat/SidebarMiddle.vue`

- [ ] **Step 1: 写 `frontend/src/components/chat/ChatInput.vue`**

```vue
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
    <button v-else class="send-button stop" @click="emit('stop')">停止生成</button>
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
  props.disabled ? 'Agent 正在工作…' : '描述你的任务，Enter 发送，Shift+Enter 换行',
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
```

- [ ] **Step 2: 写 `frontend/src/components/chat/TaskHeaderBar.vue`**

```vue
<template>
  <header class="task-header">
    <input
      v-if="editing"
      ref="titleInput"
      v-model="draftTitle"
      class="title-input"
      @blur="commit"
      @keydown.enter="commit"
      @keydown.esc="cancel"
    />
    <h2 v-else class="title" @click="startEditing">
      {{ task?.title ?? '未选择任务' }}
    </h2>

    <div class="actions">
      <button class="action" :disabled="!task" @click="startEditing">重命名</button>
      <button class="action" :disabled="!task" @click="archive">归档</button>
      <button class="action" :disabled="!task" @click="clearContext">清空上下文</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useWorkspaceStore } from '@/store/workspaces'
import { useSessionStore } from '@/store/session'

const store = useWorkspaceStore()
const session = useSessionStore()

const editing = ref(false)
const draftTitle = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

async function startEditing(): Promise<void> {
  if (!store.activeTask) return
  draftTitle.value = store.activeTask.title
  editing.value = true
  await nextTick()
  titleInput.value?.focus()
}

function commit(): void {
  if (store.activeTaskId) {
    store.renameTask(store.activeTaskId, draftTitle.value)
  }
  editing.value = false
}

function cancel(): void {
  editing.value = false
}

function archive(): void {
  if (store.activeTaskId) {
    store.archiveTask(store.activeTaskId)
  }
}

function clearContext(): void {
  session.reset()
}
</script>

<style scoped>
.task-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--color-border);
  min-height: 48px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  flex: 1;
  cursor: text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  border: 1px solid #165dff;
  border-radius: 4px;
}

.actions {
  display: flex;
  gap: 4px;
}

.action {
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
}

.action:disabled {
  color: #c9cdd4;
  cursor: not-allowed;
}

.action:not(:disabled):hover {
  background: var(--color-bg-subtle);
}
</style>
```

- [ ] **Step 3: 写 `frontend/src/components/chat/SidebarMiddle.vue`**

```vue
<template>
  <section class="sidebar-middle">
    <TaskHeaderBar />
    <MessageList />
    <ChatInput
      :disabled="session.isStreaming"
      @send="send"
      @stop="stop"
    />
  </section>
</template>

<script setup lang="ts">
import TaskHeaderBar from './TaskHeaderBar.vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'
import { useChat } from '@/composables/useChat'

const session = useSessionStore()
const workspace = useWorkspaceStore()
const { send, stop } = useChat()
</script>

<style scoped>
.sidebar-middle {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  min-width: 0;
}
</style>
```

> 注：`useChat` 在 Task 11 实现；本任务先提交组件，Task 11 完成后整体可运行。

- [ ] **Step 4: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/components/chat/ChatInput.vue \
        frontend/src/components/chat/TaskHeaderBar.vue \
        frontend/src/components/chat/SidebarMiddle.vue
git commit -m "feat: frontend: add chat input, task header and middle pane"
```

---

## Task 11: 右栏 — 产物预览 / 文件 / Diff / 下载

**Files:**
- Create: `frontend/src/components/artifacts/PreviewPane.vue`
- Create: `frontend/src/components/artifacts/FileTreePane.vue`
- Create: `frontend/src/components/artifacts/DiffPane.vue`
- Create: `frontend/src/components/artifacts/DownloadPane.vue`
- Create: `frontend/src/components/artifacts/ArtifactTabs.vue`
- Create: `frontend/src/components/artifacts/SidebarRight.vue`

- [ ] **Step 1: 写 `frontend/src/components/artifacts/PreviewPane.vue`**

```vue
<template>
  <div class="preview-pane">
    <div v-if="!active" class="empty">选择左侧产物以预览</div>

    <template v-else>
      <div class="preview-toolbar">
        <span class="file-name">{{ active.filePath }}</span>
        <a class="toolbar-action" :href="active.url" target="_blank" rel="noopener">
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

      <img v-else-if="active.type === 'image'" class="preview-image" :src="active.url" alt="" />

      <pre v-else-if="active.type === 'markdown'" class="preview-markdown">{{ markdownSource }}</pre>

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
    if (!artifact || (artifact.type !== 'markdown' && artifact.type !== 'text')) return

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
```

- [ ] **Step 2: 写 `frontend/src/components/artifacts/FileTreePane.vue`**

```vue
<template>
  <div class="file-tree">
    <p v-if="files.length === 0" class="empty">暂无文件</p>
    <ul v-else class="tree-list">
      <li
        v-for="file in files"
        :key="file.path"
        class="file-item"
        :class="{ active: file.path === selectedPath }"
        @click="selectedPath = file.path"
      >
        <span class="file-icon">{{ file.isDir ? '▸' : '·' }}</span>
        <span class="file-name">{{ file.path }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

interface FileEntry {
  path: string
  isDir: boolean
}

const props = defineProps<{ taskId: string | null }>()

const files = ref<FileEntry[]>([])
const selectedPath = ref('')

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
</script>

<style scoped>
.file-tree {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.tree-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.file-item {
  display: flex;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.file-item:hover {
  background: var(--color-bg-subtle);
}

.file-item.active {
  background: #e8f3ff;
  color: #165dff;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 12px;
  margin-top: 24px;
}
</style>
```

- [ ] **Step 3: 写 `frontend/src/components/artifacts/DiffPane.vue`**

```vue
<template>
  <div class="diff-pane">
    <div class="diff-toolbar">
      <button class="toolbar-action" @click="reload">刷新</button>
      <span class="diff-hint">{{ summary }}</span>
    </div>
    <pre v-if="diff" class="diff-content">{{ diff }}</pre>
    <p v-else class="empty">工作区没有未提交的变更</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps<{ taskId: string | null }>()

const diff = ref('')

const summary = computed(() => {
  if (!diff.value) return '无变更'
  const added = (diff.value.match(/^\+[^+]/gm) ?? []).length
  const removed = (diff.value.match(/^-[^-]/gm) ?? []).length
  return `+${added} / -${removed}`
})

async function reload(): Promise<void> {
  if (!props.taskId) {
    diff.value = ''
    return
  }
  try {
    const response = await fetch(`/api/tasks/${props.taskId}/git-diff`)
    if (!response.ok) throw new Error(String(response.status))
    const body = await response.json()
    diff.value = body.diff ?? ''
  } catch {
    diff.value = ''
  }
}

onMounted(reload)
watch(() => props.taskId, reload)
</script>

<style scoped>
.diff-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.diff-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
}

.toolbar-action {
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}

.diff-hint {
  margin-left: auto;
  color: #86909c;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.diff-content {
  flex: 1;
  margin: 0;
  padding: 10px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: pre;
  background: var(--color-bg-subtle);
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 12px;
  margin-top: 24px;
}
</style>
```

- [ ] **Step 4: 写 `frontend/src/components/artifacts/DownloadPane.vue`**

```vue
<template>
  <div class="download-pane">
    <p v-if="artifacts.length === 0" class="empty">暂无产物</p>

    <ul v-else class="artifact-list">
      <li v-for="artifact in artifacts" :key="artifact.filePath" class="artifact-item">
        <span class="artifact-icon">{{ iconFor(artifact.type) }}</span>
        <span class="artifact-name">{{ artifact.filePath }}</span>
        <a class="download-link" :href="artifact.url" :download="artifact.filePath">
          下载
        </a>
      </li>
    </ul>

    <footer v-if="artifacts.length > 0" class="pane-footer">
      <a class="download-all" :href="downloadAllUrl">打包下载全部</a>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/store/session'
import type { Artifact } from '@/types'

const props = defineProps<{ taskId: string | null }>()

const session = useSessionStore()
const artifacts = computed(() => session.artifacts)
const downloadAllUrl = computed(() => `/api/tasks/${props.taskId}/artifacts/download`)

function iconFor(type: Artifact['type']): string {
  switch (type) {
    case 'html':
      return '⬡'
    case 'markdown':
      return '¶'
    case 'image':
      return '▣'
    default:
      return '▤'
  }
}
</script>

<style scoped>
.download-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
}

.artifact-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-y: auto;
}

.artifact-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 6px;
  font-size: 12px;
}

.artifact-item:hover {
  background: var(--color-bg-subtle);
}

.artifact-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-link {
  color: #165dff;
  text-decoration: none;
}

.pane-footer {
  border-top: 1px solid var(--color-border);
  padding-top: 8px;
}

.download-all {
  display: block;
  text-align: center;
  padding: 6px;
  color: #165dff;
  text-decoration: none;
  font-size: 12px;
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 12px;
  margin-top: 24px;
}
</style>
```

- [ ] **Step 5: 写 `frontend/src/components/artifacts/ArtifactTabs.vue`**

```vue
<template>
  <nav class="artifact-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      class="tab"
      :class="{ active: tab.id === activeTab }"
      @click="emit('update:activeTab', tab.id)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<script setup lang="ts">
export type ArtifactTabId = 'preview' | 'files' | 'diff' | 'download'

defineProps<{ activeTab: ArtifactTabId }>()
const emit = defineEmits<{ 'update:activeTab': [tab: ArtifactTabId] }>()

const tabs: Array<{ id: ArtifactTabId; label: string }> = [
  { id: 'preview', label: '产物预览' },
  { id: 'files', label: '全部文件' },
  { id: 'diff', label: '文件变更' },
  { id: 'download', label: '下载' },
]
</script>

<style scoped>
.artifact-tabs {
  display: flex;
  border-bottom: 1px solid var(--color-border);
  padding: 0 4px;
}

.tab {
  padding: 8px 10px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 12px;
  color: #4e5969;
  cursor: pointer;
}

.tab.active {
  color: #165dff;
  border-bottom-color: #165dff;
}
</style>
```

- [ ] **Step 6: 写 `frontend/src/components/artifacts/SidebarRight.vue`**

```vue
<template>
  <aside class="sidebar-right">
    <ArtifactTabs v-model:active-tab="activeTab" />

    <div class="pane-body">
      <PreviewPane v-if="activeTab === 'preview'" :artifact="activeArtifact" />
      <FileTreePane v-else-if="activeTab === 'files'" :task-id="taskId" />
      <DiffPane v-else-if="activeTab === 'diff'" :task-id="taskId" />
      <DownloadPane v-else :task-id="taskId" />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ArtifactTabs, { type ArtifactTabId } from './ArtifactTabs.vue'
import PreviewPane from './PreviewPane.vue'
import FileTreePane from './FileTreePane.vue'
import DiffPane from './DiffPane.vue'
import DownloadPane from './DownloadPane.vue'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'

const session = useSessionStore()
const workspace = useWorkspaceStore()

const activeTab = ref<ArtifactTabId>('preview')

const taskId = computed(() => workspace.activeTaskId)
const activeArtifact = computed(() => session.artifacts[0] ?? null)
</script>

<style scoped>
.sidebar-right {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border);
  background: #fff;
  min-width: 0;
}

.pane-body {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
</style>
```

- [ ] **Step 7: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/components/artifacts/
git commit -m "feat: frontend: add right pane with preview, files, diff and download"
```

---

## Task 12: 三栏布局、SSE 接线与联调

**Files:**
- Create: `frontend/src/composables/useChat.ts`
- Create: `frontend/src/components/layout/ThreeColumnLayout.vue`
- Modify: `frontend/src/App.vue`
- Create: `frontend/tests/composables/useChat.spec.ts`

- [ ] **Step 1: 写失败的测试 `frontend/tests/composables/useChat.spec.ts`**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'
import { useChat } from '@/composables/useChat'

describe('useChat', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('appends the user message and opens an assistant turn', async () => {
    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')
    expect(session.messages[0].role).toBe('user')
    expect(session.messages[1].role).toBe('assistant')
  })

  it('requires an active task', async () => {
    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')
    // Without a task there is nowhere to run, so only the user message
    // is recorded and no turn is opened.
    expect(session.messages).toHaveLength(1)
  })

  it('does not send while a turn is already streaming', async () => {
    const workspace = useWorkspaceStore()
    workspace.setWorkspaces([
      {
        id: 'w1',
        name: 'W',
        tasks: [
          {
            id: 't1',
            title: 'T',
            workspaceId: 'w1',
            status: 'running',
            updatedAt: '',
            hasArtifacts: false,
          },
        ],
      },
    ])
    workspace.selectTask('t1')

    const session = useSessionStore()
    session.beginAssistantTurn()

    const { send } = useChat()
    await send('第二条')
    expect(session.messages).toHaveLength(1)
  })

  it('stop resets the streaming state', async () => {
    const session = useSessionStore()
    session.beginAssistantTurn()
    const { stop } = useChat()
    stop()
    expect(session.isStreaming).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL — 无法解析 `@/composables/useChat`

- [ ] **Step 3: 写实现 `frontend/src/composables/useChat.ts`**

```ts
/**
 * Wiring between the chat input and the agent stream.
 *
 * Two modes share one code path:
 *
 * * **Live** — `POST /api/chat` returns an SSE stream that is consumed
 *   frame by frame.
 * * **Mock** — when `VITE_USE_MOCK` is set, the local simulator stands in.
 *   This is what lets the workbench be built and demoed without a backend.
 *
 * Switching between them is a build-time flag rather than a code change,
 * so integration testing is a one-line diff.
 */
import { ref } from 'vue'
import { apiClient } from '@/api/client'
import { parseSseFrame, splitSseBuffer } from '@/api/events'
import { mockTurn } from '@/mock/sse-server'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export function useChat() {
  const session = useSessionStore()
  const workspace = useWorkspaceStore()
  const abortController = ref<AbortController | null>(null)

  /**
   * Send one message and stream the reply into the session store.
   *
   * @param message - The user's message.
   */
  async function send(message: string): Promise<void> {
    if (session.isStreaming) return

    // Record the user's turn before checking for a task, so the transcript
    // shows what was typed even if there is nowhere to run it.
    session.addUserMessage(message)

    const taskId = workspace.activeTaskId
    if (!taskId) return

    session.beginAssistantTurn()

    if (USE_MOCK) {
      for await (const frame of mockTurn(message)) {
        const parsed = parseSseFrame(frame)
        if (parsed) session.applyFrame(parsed)
      }
      return
    }

    const controller = new AbortController()
    abortController.value = controller

    try {
      for await (const parsed of apiClient.stream('/api/chat', {
        task_id: taskId,
        message,
      })) {
        session.applyFrame(parsed as never)
      }
    } catch {
      // The stream can fail mid-flight (backend restart, network drop).
      // Surface it in the transcript rather than leaving a spinner that
      // never resolves.
      session.applyFrame({
        event: 'text_delta',
        data: { text: '\n\n[连接中断]' },
      } as never)
      session.applyFrame({ event: 'done', data: { task_status: 'failed' } } as never)
    } finally {
      abortController.value = null
    }
  }

  /** Abort the in-flight turn. */
  function stop(): void {
    abortController.value?.abort()
    session.applyFrame({ event: 'done', data: { task_status: 'aborted' } } as never)
  }

  return { send, stop }
}
```

- [ ] **Step 4: 加环境变量支持到 `vite.config.ts`**

在 `defineConfig` 的返回对象中追加：

```ts
  define: {
    // Set VITE_USE_MOCK=true to run the UI without a backend.
    'import.meta.env.VITE_USE_MOCK': JSON.stringify(
      process.env.VITE_USE_MOCK ?? 'false',
    ),
  },
```

- [ ] **Step 5: 写 `frontend/src/components/layout/ThreeColumnLayout.vue`**

```vue
<template>
  <div class="three-column">
    <Splitpanes class="default-theme" @resize="onResize">
      <Pane v-if="!leftCollapsed" :size="leftSize" min-size="14" max-size="34">
        <SidebarLeft />
      </Pane>

      <Pane :size="middleSize" min-size="30">
        <SidebarMiddle />
      </Pane>

      <Pane v-if="!rightCollapsed" :size="rightSize" min-size="18" max-size="42">
        <SidebarRight />
      </Pane>
    </Splitpanes>

    <button
      class="collapse-toggle toggle-left"
      :style="{ left: leftCollapsed ? '0' : `${leftSize}%` }"
      :aria-label="leftCollapsed ? '展开左侧栏' : '折叠左侧栏'"
      @click="leftCollapsed = !leftCollapsed"
    >
      {{ leftCollapsed ? '▸' : '◂' }}
    </button>

    <button
      class="collapse-toggle toggle-right"
      :style="{ right: rightCollapsed ? '0' : `${rightSize}%` }"
      :aria-label="rightCollapsed ? '展开结果区' : '折叠结果区'"
      @click="rightCollapsed = !rightCollapsed"
    >
      {{ rightCollapsed ? '◂' : '▸' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Pane, Splitpanes } from 'splitpanes'
import SidebarLeft from '@/components/sidebar/SidebarLeft.vue'
import SidebarMiddle from '@/components/chat/SidebarMiddle.vue'
import SidebarRight from '@/components/artifacts/SidebarRight.vue'
import { useSessionStore } from '@/store/session'

const session = useSessionStore()

const leftCollapsed = ref(false)
const rightCollapsed = ref(true) // collapsed until there is something to show

const leftSize = ref(20)
const middleSize = ref(80)
const rightSize = ref(30)

// Spec §1.2: the result pane opens itself when an artifact appears, so the
// user does not have to guess that there is something to look at.
watch(
  () => session.artifacts.length,
  (count, previous) => {
    if (count > (previous ?? 0)) {
      rightCollapsed.value = false
    }
  },
)

function onResize(event: Array<{ size: number }>): void {
  const sizes = event.map((pane) => pane.size)
  if (!leftCollapsed.value && !rightCollapsed.value) {
    ;[leftSize.value, middleSize.value, rightSize.value] = sizes
  } else if (leftCollapsed.value) {
    middleSize.value = sizes[0]
    rightSize.value = sizes[1]
  } else {
    leftSize.value = sizes[0]
    middleSize.value = sizes[1]
  }
}

const paneCount = computed(
  () => 3 - Number(leftCollapsed.value) - Number(rightCollapsed.value),
)
</script>

<style scoped>
.three-column {
  position: relative;
  height: 100%;
  width: 100%;
}

.collapse-toggle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 40px;
  background: #fff;
  border: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 10px;
  z-index: 10;
  padding: 0;
  color: #86909c;
}

.toggle-left {
  border-left: none;
  border-radius: 0 4px 4px 0;
}

.toggle-right {
  border-right: none;
  border-radius: 4px 0 0 4px;
}
</style>
```

- [ ] **Step 6: 替换 `frontend/src/App.vue`**

```vue
<template>
  <div class="app-shell">
    <header class="top-bar">
      <span class="brand">s_agent 工作台</span>
      <span v-if="workspace.activeTask" class="active-task">
        {{ workspace.activeTask.title }}
      </span>
    </header>

    <main class="app-body">
      <ThreeColumnLayout />
    </main>

    <SettingsDrawer />
  </div>
</template>

<script setup lang="ts">
import ThreeColumnLayout from '@/components/layout/ThreeColumnLayout.vue'
import SettingsDrawer from '@/components/sidebar/SettingsDrawer.vue'
import { useWorkspaceStore } from '@/store/workspaces'

const workspace = useWorkspaceStore()
</script>

<style scoped>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.top-bar {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
  background: #fff;
  flex-shrink: 0;
}

.brand {
  font-size: 14px;
  font-weight: 600;
}

.active-task {
  font-size: 12px;
  color: #86909c;
}

.app-body {
  flex: 1;
  min-height: 0;
}
</style>
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd frontend && npm test`
Expected: 62 passed

- [ ] **Step 8: 用 Mock 模式手工验证三栏**

Run:
```bash
cd /media/data/git/s_agent/frontend
VITE_USE_MOCK=true npm run dev
```
Expected:
- 浏览器打开 `http://localhost:5173`
- 左栏显示侧边栏（新建任务/搜索/用户头像）
- 横向拖拽可调整分栏宽度；点击箭头可折叠左右栏
- 中栏输入框可输入；发送后看到思考块、工具卡片、逐字输出
- 输入"帮我生成一个网页"后右栏自动展开并显示产物预览 Tab
- 输入"删除所有文件"后出现橙色确认卡片

> 首次运行左栏为空（无工作区数据）。若需演示数据，可在 `App.vue` 的 `onMounted` 中调用 `workspace.setWorkspaces([...])` 注入，或在 Task 5 的 store 中加载 `/api/workspaces`（阶段二补 REST 后端）。

- [ ] **Step 9: 用真实后端联调**

Run（两个终端）：
```bash
# 终端 1 — 后端
cd /media/data/git/s_agent
LITELLM_API_KEY=<你的key> /media/data/venv/bin/python -m uvicorn server.main:app --port 8000

# 终端 2 — 前端
cd /media/data/git/s_agent/frontend
npm run dev
```
Expected: 不经 mock，输入消息后由真实 `v-flash` 流式回复。

- [ ] **Step 10: Commit**

```bash
cd /media/data/git/s_agent
git add frontend/src/composables/useChat.ts \
        frontend/src/components/layout/ThreeColumnLayout.vue \
        frontend/src/App.vue frontend/vite.config.ts \
        frontend/tests/composables/useChat.spec.ts
git commit -m "feat: frontend: wire three-column layout to the agent stream"
```

---

## Part 2 完成标志

- [ ] `npm test` 全绿（62 个测试）
- [ ] `npm run dev` 三栏渲染正常，左右栏可拖拽调宽与折叠
- [ ] Mock 模式下：思考块、工具卡片、逐字输出、产物预览、HITL 确认卡片全部可见
- [ ] `VITE_USE_MOCK` 关闭后与真实后端 SSE 联调通过
- [ ] `src/api/events.ts` 的事件名与后端 `server/service/events.py` 完全一致

## 已知遗留（留待阶段二）

- `/api/workspaces` 与 `/api/tasks` 的 REST 端点后端尚未实现，前端工作区树需注入数据或等后端补齐
- `PreviewPane` 的 Markdown 用 `<pre>` 原样展示，未做富文本渲染
- `DiffPane` 用 `<pre>` 展示 unified diff，未接入 `vue-diff` 的并排视图
- `FileTreePane` 与 `DownloadPane` 依赖 `/api/tasks/{id}/files` 与 `artifacts/download` 端点（后端待实现）
- HITL 的 `resolveConfirm` 只清本地状态，未回传 `/api/tasks/{id}/confirm`
