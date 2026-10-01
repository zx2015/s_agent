# 产物预览 Markdown 渲染架构设计规范

> 状态：PROPOSED  
> 日期：2026-10-01  
> 模块：`frontend/src/components/artifacts/PreviewPane.vue`, `frontend/tests/components/Artifacts.spec.ts`

---

## 一、 背景与现状分析

### 1.1 背景
在 s_agent 智能体工作台中，智能体执行投研分析、系统设计、代码开发等任务时，会向工作区根目录产出 `.md`、`.html`、`.svg`、`.png` 等交付物。
对于金融投资分析报告（如《伊利股份投资价值分析.md》），报告通常包含：
- 多级标题与结构化摘要；
- 多列财务指标对比表格（PE、毛销差、现金流比率等）；
- 重点数据加粗与引用说明；
- Mermaid 架构或业务关系流程图；
- 算式代码块与公式。

### 1.2 代码现状与缺陷
当前前端右侧栏预览组件 [`PreviewPane.vue`](file:///media/data/git/s_agent/frontend/src/components/artifacts/PreviewPane.vue#L33-L36) 的渲染逻辑如下：

```html
<!-- HTML 页面通过 iframe 预览 -->
<iframe v-if="active.type === 'html'" class="preview-frame" :src="active.url" ... />

<!-- 图片通过 img 预览 -->
<img v-else-if="active.type === 'image'" class="preview-image" :src="active.url" ... />

<!-- Markdown 文件渲染逻辑 -->
<pre
  v-else-if="active.type === 'markdown'"
  class="preview-markdown"
>{{ markdownSource }}</pre>

<!-- 纯文本渲染逻辑 -->
<pre v-else class="preview-text">{{ textSource }}</pre>
```

**问题根因**：
- 数据层：虽然通过 `fetch(artifact.url)` 成功获取了 Markdown 文本字符串，存储在 `markdownSource` 响应式变量中；
- 渲染层：直接使用原生 `<pre class="preview-markdown">` 标签包裹展示，导致 Markdown 语法的标题、表格线（`|---|`）、粗体（`**`）、无序列表等均以未排版的等宽纯文本呈现，极大地削弱了交付物的可读性与专业感。

---

## 二、 组件选型评估

针对 Markdown 渲染组件的选型，主要有两个方向：

| 方案 | 实现方式 | 优点 | 缺点 | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| **方案 A：外部第三方 Markdown 库** | 引入 `v-md-editor`、`marked` 或独立的 `markdown-it` | 可定制化程度高 | 引入冗余依赖，增加打包体积；样式与 MateChat 现存 UI 风格不一致，需大量二次样式覆写 | ❌ 不采纳 |
| **方案 B：复用 MateChat 内置 `McMarkdownCard`** | 导入 `@matechat/core` 的 `McMarkdownCard` | 1. 零新增依赖（已内置）；<br>2. 内部集成 `markdown-it`、`highlight.js`、`xss` 及 `MermaidService`；<br>3. 原生支持 GFM 表格、代码高亮与 Mermaid 图表；<br>4. 与整体 MateChat 设计语言和浅深色主题完美契合；<br>5. 已在 `AssistantMessage.vue` 中稳定运行。 | 需要针对预览面板容器微调排版与滚动样式 | ✅ **首选推荐** |

---

## 三、 详细架构设计

### 3.1 数据流与渲染架构

```
                     ┌─────────────────────────────────────────┐
                     │         Task Artifacts (工作区产物)       │
                     └────────────────────┬────────────────────┘
                                          │ 选择 .md 产物
                                          ▼
                     ┌─────────────────────────────────────────┐
                     │          PreviewPane.vue (预览面板)       │
                     └────────────────────┬────────────────────┘
                                          │ fetch(artifact.url)
                                          ▼
                             markdownSource.value (原始MD文本)
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   │                                             │
                   ▼ (渲染模式)                                   ▼ (源码模式，可选切换)
┌─────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│        McMarkdownCard (核心渲染)         │   │            pre (纯文本源码)             │
│ - 编译 GFM 语法 (标题/粗体/引用/列表)      │   │ - 等宽字体显示                           │
│ - 格式化渲染 Markdown 数据表格            │   │ - 用于开发者检查原始文件排版              │
│ - highlight.js 语法高亮代码块           │   └─────────────────────────────────────────┘
│ - MermaidService 动态绘制图表           │
└─────────────────────────────────────────┘
```

### 3.2 模板层设计 (Template Structure)

在 `PreviewPane.vue` 中扩展工具栏与预览区域：

```html
<template>
  <div class="preview-pane">
    <div v-if="!active" class="empty">选择左侧产物以预览</div>

    <template v-else>
      <div class="preview-toolbar">
        <span class="file-name">{{ active.filePath }}</span>
        <div class="toolbar-actions">
          <!-- 针对 Markdown 产物增加“渲染/源码”切换按钮 -->
          <button
            v-if="active.type === 'markdown'"
            class="toolbar-btn"
            @click="isRawMode = !isRawMode"
          >
            {{ isRawMode ? '预览效果' : '查看源码' }}
          </button>
          <button
            class="toolbar-btn"
            @click="copyContent"
          >
            {{ copySuccess ? '已复制' : '复制内容' }}
          </button>
          <a
            class="toolbar-action"
            :href="active.url"
            target="_blank"
            rel="noopener"
          >
            新标签打开
          </a>
        </div>
      </div>

      <!-- HTML 网页预览 -->
      <iframe
        v-if="active.type === 'html'"
        class="preview-frame"
        :src="active.url"
        sandbox="allow-scripts allow-forms"
        title="产物预览"
      />

      <!-- 图片预览 -->
      <img
        v-else-if="active.type === 'image'"
        class="preview-image"
        :src="active.url"
        alt=""
      />

      <!-- Markdown 文件：支持 McMarkdownCard 富文本渲染与源码切换 -->
      <div
        v-else-if="active.type === 'markdown'"
        class="preview-markdown-container"
      >
        <pre v-if="isRawMode" class="preview-markdown-raw">{{ markdownSource }}</pre>
        <div v-else class="preview-markdown-body">
          <McMarkdownCard
            :content="markdownSource"
            :enable-mermaid="true"
          />
        </div>
      </div>

      <!-- 纯文本兜底 -->
      <pre v-else class="preview-text">{{ textSource }}</pre>
    </template>
  </div>
</template>
```

### 3.3 样式系统与视觉排版规范 (Styling & Typography)

1. **容器排版与滚动**：
   - `.preview-markdown-container`：`flex: 1; min-height: 0; overflow-y: auto; background: var(--color-bg);`；
   - `.preview-markdown-body`：`padding: 24px 28px; font-size: 14px; line-height: 1.75; color: var(--color-text);`；
2. **表格（GFM Table）视觉增强**：
   - 在产物预览场景下，表格需具备清晰的网格边界：
     - 表头 `th`：浅灰色/暗灰底色（`background: var(--color-bg-subtle)`），字重加粗，内边距 `8px 12px`；
     - 单元格 `td`：带柔和细边框（`border: 1px solid var(--color-border)`），左右内边距对齐；
     - 表格允许横向滚动（`overflow-x: auto`），避免大列宽挤压布局。
3. **代码块与图表**：
   - 代码块保持内边距与圆角（`border-radius: 6px`）；
   - 引用块（`blockquote`）添加左侧强调边条（`border-left: 3px solid var(--color-primary, #1890ff)`）；
### 3.4 “新标签打开”独立预览页设计 (Standalone Artifact Viewer)

#### 3.4.1 痛点
当用户在右侧预览栏点击「新标签打开」时，原逻辑直接将链接指向后端的物理文件流接口：
`/api/tasks/{task_id}/artifacts/preview/{rel_path}`
- 后端 FastAPI 的 `FileResponse` 返回的是无格式的原始文本（Content-Type 为 `text/markdown` 或 `text/plain`）；
- 浏览器新标签页仅渲染黑白纯文本或触发文件下载，无法享受到工作台内的格式化排版、表格线和代码高亮。

#### 3.4.2 解决方案
设计基于 URL 参数的**独立产物阅读器（StandaloneArtifactViewer.vue）**：
1. **URL 协议规范**：
   - 当产物为 Markdown（`.md`）时，「新标签打开」指向前端应用路由：
     `/?view=artifact&taskId={taskId}&filePath={encodedFilePath}&type=markdown`
   - 当产物为原生 HTML 时，依然直接在独立标签页打开 `active.url`（由浏览器原生解析展示网页）。
2. **应用根挂载路由（App.vue）**：
   - `App.vue` 初始化时检查 `window.location.search`；
   - 若检测到 `view === 'artifact'`，挂载全屏专用的 `<StandaloneArtifactViewer />`，隐藏三栏工作台与任务侧边栏，提供沉浸式报告阅读体验；
3. **独立阅读器功能与视觉**：
   - 顶部导航条：展示报告名称、Markdown 类型徽标、沉浸式返回工作台链接；
   - 交互操作：支持「预览效果 / 查看源码」切换、一键「复制内容」、一键「下载文件」、以及实时深色/浅色主题切换；
   - 正文容器：全屏居中阅读排版（最大宽度 960px 或全屏），内嵌 `<McMarkdownCard :content="content" :enable-mermaid="true" />`，支持长文档平滑滚动与打印优化。

---

## 四、 实施步骤

1. **编写设计文档**：落盘本规范 `docs/specs/2026-10-01-artifact-markdown-preview-design.md`；
2. **实现独立产物阅读器组件**：
   - 新建 `frontend/src/components/artifacts/StandaloneArtifactViewer.vue`，集成 `McMarkdownCard` 与主题控制；
3. **修改 `App.vue`**：
   - 识别 `/?view=artifact` 查询参数，条件渲染独立预览器；
4. **修改 `PreviewPane.vue` 与 `SidebarRight.vue`**：
   - 传递 `taskId` 并动态计算 `openInNewTabUrl`，使 Markdown 产物链接到独立阅读器；
5. **完善自动化测试**：
   - 在 `frontend/tests/components/Artifacts.spec.ts` 中新增针对独立阅读器和新标签链接计算的单测；
6. **回归测试与验证**：
   - 执行 `npm test`（Vitest 100% 通过）与后端 `pytest`；
   - 在浏览器中点击「新标签打开」，验证新标签页中使用 `McMarkdownCard` 渲染的效果。

