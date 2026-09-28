# 前端三栏设计需求文档：Agent 智能工作台 (Workbench)

> **文档版本**：v1.0
> **创建日期**：2026-09-28
> **关联阶段**：阶段三（前端实现），与阶段一（单 Agent 内核）并行开发
> **文档位置**：`docs/specs/2026-09-28-frontend-three-column-workbench.md`

---

## 一、架构定位与设计哲学

### 1.1 总体布局

采用类 IDE 的**「左-中-右」三栏弹性工作台（Workbench）**架构：

```
+----------------------------------------------------------------------------------------------------+
|                                      Top Bar (全局状态 / 导航)                                      |
+-------------------+----------------------------------------------+---------------------------------+
|   1. 左侧边栏     |           2. 中间对话区 (核心)                |          3. 右侧结果区          |
|                   |                                              |                                 |
| - 搜索/过滤       | [顶部] 任务标题栏 + 操作 (重命名/归档)       | [顶部 Tabs]                     |
| - 工作区分组      |                                              |   预览 | 文件 | Diff | 下载     |
|   v 项目 A        | [中部] 消息流 (滚动区)                       |                                 |
|     * 任务 1      |   - 用户指令气泡 (McBubble)                  | [内容区]                        |
|     * 任务 2      |   - Agent 思考过程 (折叠)                    | - HTML/MD 实时预览 (iframe)     |
|   > 项目 B        |   - 工具执行卡片 (Bash/File/Task)            | - 文件树浏览器                  |
|                   |   - HITL 确认卡片                            | - Git Diff 差异比对             |
|                   |                                              | - 产物下载列表                  |
| [底部]            | [底部] 自然语言输入框 (McInput)              |                                 |
| 用户头像 -> 设置  |                                              |                                 |
+-------------------+----------------------------------------------+---------------------------------+
| <拖拽调宽/折叠>   |                   (主视区)                   |                 <拖拽调宽/折叠> |
+----------------------------------------------------------------------------------------------------+
```

### 1.2 核心交互原则

1. **分栏可弹性伸缩**：左右两栏均支持**拖拽调整宽度**（min 200px, max 500px）与**一键折叠/展开**；右栏在初始无产物时**默认收起**，检测到新产物生成时**自动展开**。
2. **中间对话为主视区**：中间对话区域宽度自适应，保证打字机流式输出的阅读舒适度。
3. **数据层解耦**：前端通过 Mock 数据协议与后端并行开发，不阻塞于后端内核完工。

---

## 二、三栏功能模块详细定义

### 2.1 第一栏：左侧边栏 (Navigation & Task Manager)

**组织模型**：**双层架构（工作区 Workspace / Folder -> 任务 Task）**。

#### 功能项
- **L-1 顶部快捷操作**：
  - 「新建任务」按钮（快捷键 `Ctrl/Cmd + N`）
  - 全局搜索框：实时过滤任务标题与关键词
- **L-2 树形任务列表**：
  - 按**工作区 / 项目**分组（可折叠树形结构）
  - 每个任务节点展示：
    - 任务状态图标（进行中 / 已完成 / 挂起 / 失败）
    - 任务标题（双击可就地重命名）
    - 最后活跃时间
    - 产物标记（若该任务有产物，显示一个小图标）
  - 右键上下文菜单：重命名、归档、移入其他工作区、彻底删除
- **L-3 底部用户与系统入口**：
  - 用户头像与名称
  - 点击头像弹出**设置抽屉 (Settings Drawer)**：
    - 模型选择（LiteLLM 模型列表选择，默认 `v-flash`）
    - API 端点配置
    - 工作区根目录路径展示
    - 系统主题切换（深色 / 浅色）
    - HITL 权限严格程度（全确认 / 高危确认 / 自动放行）

---

### 2.2 第二栏：中间对话区 (Chat & Execution Stream)

基于华为 DevUI **MateChat** 组件库构建，作为核心交互主战场。

#### 功能项
- **M-1 顶部任务状态栏**：
  - 当前激活的任务标题（可原地编辑）
  - 所属工作区路径标签
  - 操作按钮组：
    - 「归档任务」
    - 「清空会话上下文」
    - 「强制中断当前执行」
- **M-2 滚动消息列表（基于 `McBubble` 与自定义卡片）**：
  - **用户消息**：标准右侧气泡，展示用户下达的自然语言指令。
  - **Agent 思考链（Thinking Block）**：
    - `v-flash` 输出的 `reasoning_content` 单独渲染为折叠思考块（默认收起，点击展开），带计时器。
  - **执行过程与进度（Tool Calls）**：
    - 工具执行卡片化：展示工具名（如 `Bash: npm run build`）、参数、执行中 Spinner、执行结果（折叠）。
    - 阶段一 12 个内置工具的专属卡片样式（文件读写、Task 管理等）。
  - **HITL 确认交互卡片**：
    - 当收到 `RequireUserConfirmEvent`（如高危 rm 操作）时，在消息流最后插入操作确认卡片（「允许执行」「拒绝」「修改参数」），用户点击后回传事件。
  - **最终文本回复**：标准左侧气泡，支持 Markdown 渲染（代码高亮、表格、公式）。
- **M-3 底部输入框（基于 `McInput` / `McLayoutSender`）**：
  - 多行自然语言输入，支持快捷键提交（`Enter` 发送，`Shift + Enter` 换行）
  - 附带附件/上下文引用按钮（阶段一占位）
  - Agent 正在生成时，发送按钮变为「停止生成」

---

### 2.3 第三栏：右侧结果区 (Artifacts & Inspector)

聚焦呈现 Agent 执行任务产生的**最终产物与代码变更**。

#### 顶部选项卡设计
包含 4 个核心 Tab 视图：

| Tab | 名称 | 展示内容 | 交互技术方案 |
|-----|------|---------|-------------|
| **Tab 1** | **产物预览** | HTML / Markdown / 图片 / 文本 | **后端受控文件服务 + 沙箱 `iframe`**（HTML 隔离渲染）/ Markdown 渲染器 |
| **Tab 2** | **全部文件** | 当前任务工作区完整文件树 | 虚拟文件树组件 + 点击文件在右侧就地只读查看 |
| **Tab 3** | **文件变更 (Diff)** | 本次任务或历史修改的代码比对 | **基于 Git Diff** + Monaco Editor / `vue-diff` 视图 |
| **Tab 4** | **可下载清单** | 所有生成物、报表、导出文件的列表 | 列表卡片 + 单文件一键下载 / 一键打包 ZIP 下载 |

#### 详细规格

- **R-1 产物预览 (Preview)**：
  - **HTML 预览**：指向后端静态服务端点 `GET /api/tasks/{task_id}/artifacts/preview/*`，塞入带 `sandbox="allow-scripts allow-same-origin"` 的 `iframe`。
  - **Markdown 预览**：使用内嵌渲染器实时呈现。
  - **第一阶段边界（已拍板）**：阶段三**明确不预览** `.pptx` / `.docx`，这两类仅展示大图标、文件大小与「下载」按钮。
- **R-2 文件变更 (Diff 视图 - 已拍板方案)**：
  - 后端将任务目录初始化为 Git 仓库。
  - Agent 每轮工具执行前后记录变更，前端调用 `GET /api/tasks/{task_id}/git-diff` 获取标准 unified diff 文本。
  - 前端使用 `vue-diff` 或 Monaco Diff Editor 展示 Side-by-Side 或 Inline 差异，高亮增删改。
- **R-3 内置简单导航条**：
  - 预览区顶部带简易控制栏：刷新按钮、复制链接、在外部新标签页打开按钮。

---

## 三、前后端通讯协议契约 (SSE 规范)

通讯协议遵循**纯 SSE (Server-Sent Events)** 规范：

### 3.1 端点设计

- **创建/唤醒对话**：`POST /api/chat`
  - 入参：`{ task_id: string, message: string }`
  - 响应：建立长连接，返回 `Content-Type: text/event-stream`

- **任务管理 REST 端点**：
  - `GET /api/workspaces`：获取工作区树与任务列表
  - `POST /api/tasks`：新建任务
  - `PATCH /api/tasks/{task_id}`：重命名/更新任务
  - `GET /api/tasks/{task_id}/files`：获取工作区文件树
  - `GET /api/tasks/{task_id}/git-diff`：获取当前 git diff
  - `GET /api/tasks/{task_id}/artifacts/download`：打包下载产物

- **HITL 确认端点**：
  - `POST /api/tasks/{task_id}/confirm`：回传用户决策 `{ reply_id: string, action: "allow" | "deny" }`

### 3.2 SSE 事件流格式

```json
// 1. 思考增量
event: thinking_delta
data: {"text": "正在分析需求..."}

// 2. 正文文本增量
event: text_delta
data: {"text": "我已经为你生成了页面原型。"}

// 3. 工具调用开始
event: tool_call_start
data: {"call_id": "c1", "tool": "Write", "args": {"file_path": "index.html"}}

// 4. 工具调用结束
event: tool_call_end
data: {"call_id": "c1", "status": "success", "result_summary": "写入成功 (1.2KB)"}

// 5. 产物生成通知（通知右侧刷新）
event: artifact_created
data: {"type": "html", "file_path": "index.html", "url": "/api/tasks/t1/artifacts/preview/index.html"}

// 6. HITL 权限请求
event: require_confirm
data: {"reply_id": "r1", "command": "rm -rf build", "reason": "高危命令需要人工确认"}

// 7. 对话结束
event: done
data: {"task_status": "completed"}
```

---

## 四、前端技术选型清单

- **基础脚手架**：Vue 3 + TypeScript + Vite
- **对话核心库**：`@matechat/core` + `vue-devui` + `@devui-design/icons`
- **分栏布局组件**：`splitpanes`（Vue 3 优秀的分栏拖拽调整库）
- **代码与 Diff 渲染**：`vue-diff` 或 `monaco-editor`
- **Markdown 引擎**：`markdown-it` + `highlight.js`
- **状态管理**：`pinia`（管理全局任务树、当前会话消息、设置）
- **Mock 服务**：前端自带本地 SSE Mock 脚本，支持在脱离后端时独立调试 UI

---

## 五、前后端并行开发隔离机制

为了遵守用户「前后端并行开发」的决策：

1. **协议优先**：前后端严格按上述第三节的 SSE 事件与 REST 端点为准绳。
2. **前端开发期 Mock**：
   - 前端工程内建 `src/mock/sse-server.ts`，模拟真实打字机、思考链、工具执行卡片及产物生成事件。
   - 前端开发者在无 Python 环境时依然可以 100% 跑通 UI、分栏伸缩与预览。
3. **联调期**：将前端 Vite 代理（`vite.config.ts` 中的 `server.proxy`）指向后端 `http://localhost:8000` 即可一键联调。

---

## Related

- [2026-09-28-stage1-single-agent-design.md](2026-09-28-stage1-single-agent-design.md) — 阶段一后端单 Agent 内核 Spec
- [../../CLAUDE.md](../../CLAUDE.md) — 项目全局规范
- [../../TODO.md](../../TODO.md) — 项目待办清单
