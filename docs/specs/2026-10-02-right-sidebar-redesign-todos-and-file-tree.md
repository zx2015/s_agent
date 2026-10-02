# 右侧边栏交互重构：待办任务与可折叠全部文件树设计规范

## 1. 背景与现状分析

在现有的三栏工作台设计中，右侧边栏（`SidebarRight.vue`）承担了产出物与任务执行细节的展示功能，共包含 5 个标签页：
- **产物预览 (`preview`)**：单文件内嵌预览（支持 Markdown/HTML/图片），占据了大量空间，且用户通常更习惯在新页面或大屏中深度阅读研报；
- **待办 (`todos`)**：展示 Agent 执行过程中的多步骤规划与待办任务列表；
- **全部文件 (`files`)**：原本仅为扁平的一维文件路径列表，缺少目录层级树与折叠收起能力；
- **文件变更 (`diff`)**：展示 Git 变更差异，对于投研与内容生产任务偏冷门；
- **下载 (`download`)**：单独设立一个下载列表标签页，与文件列表割裂，增加了用户查找和下载特定文件的操作步骤。

为了简化右侧边栏的视觉负担、提升交互效率，并强化文件管理与投研产出物的浏览体验，需要对右侧边栏进行精简与重构。

---

## 2. 用户需求分解

根据用户的明确要求：
1. **标签精简**：右侧边栏只保留 **“待办”** 与 **“全部文件”** 两项；去掉 “产物预览”、“文件变更” 和 “下载” 三项；
2. **待办定位**：待办面板放置任务执行过程中产生的 Task/Todo 条目，实时反映 Agent 的步骤拆解与执行进度；
3. **全部文件目录树与折叠**：
   - 列出当前工作区目录下的文件夹和文件；
   - 支持文件夹的层级展开与折叠收起；
   - 评估 MateChat 现有组件能力，选定最佳实现方案；
4. **纯图标操作按钮**：
   - 每个文件右侧提供两个操作按钮：**预览**与**下载**；
   - **纯图标展示，严禁带有文字**；
5. **新页面预览**：
   - 点击文件预览图标后，在新浏览器标签页中打开全屏预览页面（类似于原有的在新标签页中打开预览效果）；
6. **就地下载**：
   - 点击下载图标后，直接触发对应文件的浏览器下载。

---

## 3. 技术选型与 MateChat 组件深度评估

针对用户提出的“看看 MateChat 有没有组件能达到这个效果”，我们对项目中引入的 UI 库进行了详细排查：

### 3.1 `@matechat/core` 组件库评估
- **组件清单**：`McAttachment`, `McBubble`, `McFileList`, `McHeader`, `McInput`, `McIntroduction`, `McLayoutAside`, `McLayoutContent`, `McLayoutHeader`, `McLayout`, `McLayoutSender`, `McList`, `McMarkdownCard`, `McMention`, `McPrompt`, `McToolbar`；
- **`McFileList` 分析**：
  - `McFileList` 是专为对话输入框附件上传场景设计的扁平文件列表组件；
  - 核心属性与事件为 `fileItems`, `remove`, `download`, `preview`, `retry-upload`；
  - **不支持多级目录结构、不支持文件夹展开/折叠、不支持树状层级渲染**；
  - 因此 `@matechat/core` 原生不具备目录树能力。

### 3.2 `vue-devui` (`d-tree`) 评估
- 项目 `package.json` 中已安装 `vue-devui` (^1.6.37) 及 `@devui-design/icons`；
- DevUI 提供了 `d-tree` 树形组件，但其内部数据协议与插槽机制较为沉重，对纯图标操作栏定制的样式适配成本较高，且在 Vitest JSDOM 单元测试环境下容易引发响应式虚拟滚动的 Mock 复杂度。

### 3.3 推荐方案：基于 DevUI 图标规范的高性能原生可折叠树组件
- 采用与左侧工作区树（`WorkspaceTree.vue`）高度一致的轻量、原生递归/层级折叠树设计；
- **目录图标与状态**：
  - 折叠指示器：`▸` / `▾` 或 DevUI 图标，点击文件夹名称或图标均可切换折叠态；
  - 文件夹图标：使用 DevUI 字体图标 `.icon-close-folder` / `.icon-open-folder`；
  - 文件图标：使用 DevUI 字体图标 `.icon-file`，根据扩展名区分投研研报（Markdown）、表格（Excel/CSV）或图片；
- **文件操作按钮**：
  - 预览按钮：使用 DevUI 字体图标 `.icon-preview` 或 `.icon-view`，附带 `title="预览"`，无文本；
  - 下载按钮：使用 DevUI 字体图标 `.icon-download`，附带 `title="下载"`，无文本；
- **优势**：
  - 零新增第三方依赖，打包体积轻量；
  - 与 MateChat / DevUI 整体主题风格 100% 契合；
  - 单测覆盖容易，运行稳定无 DOM 测量报错。

---

## 4. 架构设计与交互规范

### 4.1 右侧边栏结构重构（`SidebarRight.vue` & `ArtifactTabs.vue`）

- **标签枚举变更**：
  ```ts
  export type ArtifactTabId = 'todos' | 'files'
  ```
- **标签栏配置**：
  ```ts
  const tabs: Array<{ id: ArtifactTabId; label: string }> = [
    { id: 'todos', label: '待办' },
    { id: 'files', label: '全部文件' },
  ]
  ```
- **默认选中策略**：
  - 用户切换或新建任务时，默认选中 `'todos'`（待办），以优先展示任务推进步骤；若任务无待办但有产物，或用户自主切换后，记住当前激活态。
- **模板主体简化**：
  ```html
  <McLayoutAside class="sidebar-right">
    <ArtifactTabs v-model:active-tab="activeTab" />
    <div class="pane-body">
      <TodoPanel v-if="activeTab === 'todos'" />
      <FileTreePane v-else-if="activeTab === 'files'" :task-id="taskId" />
    </div>
  </McLayoutAside>
  ```
  彻底移除 `PreviewPane`、`DiffPane`、`DownloadPane` 的常驻挂载。

---

### 4.2 全部文件折叠树数据模型与算法

后端接口 `/api/tasks/{task_id}/files` 返回当前工作区的文件相对路径列表：
```json
{
  "files": [
    { "path": "summary.md", "isDir": false },
    { "path": "models", "isDir": true },
    { "path": "models/dcf.xlsx", "isDir": false },
    { "path": "wiki/entities/yili.md", "isDir": false }
  ]
}
```

前端将扁平列表转换为支持嵌套的树形数据结构（`FileTreeNode`）：

```ts
export interface FileTreeNode {
  name: string            // 节点名称（如 "models" 或 "dcf.xlsx"）
  path: string            // 相对根目录完整路径（如 "models/dcf.xlsx"）
  isDir: boolean          // 是否为目录
  children?: FileTreeNode[] // 子节点列表（目录特有，已排序）
}
```

- **排序规则**：文件夹始终排在普通文件前面；同类型按字母顺序排序；
- **折叠状态管理**：使用 `collapsedPaths = ref<Set<string>>(new Set())` 追踪折叠的目录路径，默认保持顶层目录展开以方便用户浏览；
- **空状态**：无文件时展示优雅的空状态占位提示（“当前工作区暂无产出文件”）。

---

### 4.3 文件操作按钮交互规范

在树状列表中，每个文件条目呈现如下三段布局：

```
[折叠箭头/缩进] [文件图标] [文件名 (自动截断)] --------- [操作按钮组: 预览图标 | 下载图标]
```

1. **预览操作**：
   - 元素：`<button class="action-btn preview-btn" title="在新标签页预览" @click="handlePreview(node.path)">`
   - 内部：`<i class="icon-preview" />`（纯图标，无文本标签）；
   - 动作：调用 `window.open(getPreviewUrl(node.path), '_blank')`；
   - 预览地址构造：
     - 若为 Markdown 文档（`.md`）：跳转独立渲染页面 `/?view=artifact&taskId=${taskId}&filePath=${encodeURIComponent(path)}&type=markdown`；
     - 若为 HTML/图片/PDF：直接跳转后端静态接口 `/api/tasks/${taskId}/artifacts/preview/${path}`，由浏览器或专用视图原生呈现。
2. **下载操作**：
   - 元素：`<a class="action-btn download-btn" title="下载文件" :href="getDownloadUrl(node.path)" :download="node.name">`
   - 内部：`<i class="icon-download" />`（纯图标，无文本标签）；
   - 动作：点击即触发浏览器下载当前文件；
   - 下载地址构造：`/api/tasks/${taskId}/artifacts/preview/${path}`。

---

### 4.4 独立页面预览支持优化（`StandaloneArtifactViewer.vue`）

现有 `StandaloneArtifactViewer.vue` 已经支持 `view=artifact` 的全屏渲染，本期需要确认其容错性：
- 支持从 URL 解析 `taskId` 与 `filePath`；
- 支持 Markdown 的富文本高亮渲染与源码模式切换；
- 增加顶部面包屑或返回按钮，用户新标签打开后可轻松查看并复制内容。

---

## 5. 组件变更清单与影响范围

| 文件路径 | 变更类型 | 变更说明 |
|---|---|---|
| [`frontend/src/components/artifacts/ArtifactTabs.vue`](file:///media/data/git/s_agent/frontend/src/components/artifacts/ArtifactTabs.vue) | 修改 | `tabs` 缩减为 `待办`（`todos`）和 `全部文件`（`files`）两项；类型更新 |
| [`frontend/src/components/artifacts/SidebarRight.vue`](file:///media/data/git/s_agent/frontend/src/components/artifacts/SidebarRight.vue) | 修改 | 移除 `PreviewPane`、`DiffPane`、`DownloadPane`；默认激活标签调整为 `todos` |
| [`frontend/src/components/artifacts/FileTreePane.vue`](file:///media/data/git/s_agent/frontend/src/components/artifacts/FileTreePane.vue) | 重构 | 构建多级目录折叠树，文件夹支持展开/折叠，文件附带纯图标的预览与下载按钮 |
| [`frontend/tests/components/Artifacts.spec.ts`](file:///media/data/git/s_agent/frontend/tests/components/Artifacts.spec.ts) | 修改 | 更新对 `ArtifactTabs`（两项）及 `FileTreePane`（树形、纯图标按钮、打开新标签、下载）的单元测试 |

---

## 6. 测试与验证计划

1. **组件单元测试**：
   - 验证 `ArtifactTabs` 仅渲染 `待办` 与 `全部文件` 2 个 Tab；
   - 验证 `FileTreePane` 将扁平路径转换成树状层级结构；
   - 验证文件夹点击能够正确切换展开/折叠；
   - 验证每个文件项后面包含且仅包含 2 个纯图标按钮（没有多余文字）；
   - 验证点击预览按钮触发 `window.open` 并携带正确的 URL 参数；
   - 验证下载按钮包含正确的 `download` 属性与目标文件 URL；
2. **回归与构建测试**：
   - 执行 `npm test`（Vitest），确保所有前端单测 100% 通过；
   - 执行 `npm run build`，确保 TypeScript 类型检查无报错、打包构建成功。
