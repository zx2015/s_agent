# Spec: AgentScope 内部 Todo 列表前端展示

> **状态**：v1 · 2026-09-28 · 修订者：Claude
> **关联文档**：[阶段一后端 spec](2026-09-28-stage1-single-agent-design.md)（模块 G·AgentScope Task 工具） · [阶段三前端 spec](2026-09-28-frontend-three-column-workbench.md)（§3.2 SSE 事件契约）
> **作用域**：单一功能的端到端契约说明，不引入新架构

---

## 1. 背景与目标

### 1.1 现状

AgentScope 2.0.8 提供了 4 个内置工具：`TaskCreate` / `TaskGet` / `TaskList` / `TaskUpdate`，Agent 在处理复杂任务时会自动调用它们把子步骤写入 `AgentState.tasks_context.tasks: list[Task]`，每个 `Task` 包含：

| 字段 | 用途 |
|---|---|
| `id` | 自增编号（TaskCreate 自动生成） |
| `subject` | 任务标题 |
| `description` | 详细描述 |
| `state` | `pending` / `in_progress` / `completed`（+ `deleted` 软删除） |
| `owner` | 负责人（如某个 sub-agent） |
| `blocks` / `blocked_by` | 任务依赖图（id 列表） |
| `created_at` | 创建时间（ISO 字符串） |
| `metadata` | 任意附加元数据 |

**问题**：当前 AgentScope 已把 todo 列表持久化到 Redis（随 `AgentState` 一起），但 **SSE 流不主动把 todo 变化 push 给前端**，**后端没有 `GET /api/tasks/{tid}/todos` 端点**，**前端没有渲染组件**。所以用户看不见 Agent 在做什么。

### 1.2 目标

让前端用户实时看到"Agent 内部的待办列表"，作为 Agent 工作透明化的最小可用功能（MVP）。

### 1.3 显式不做

- ❌ 编辑/新建 todo 的前端 UI（Agent 仍是权威）
- ❌ 把 todo 列表独立持久化到数据库（沿用 `AgentState` 持久化路径）
- ❌ 跨任务的 todo 共享或依赖（每个任务自己的 todo list 完全独立）
- ❌ 复杂依赖图渲染（仅展示 immediate 依赖的 `blocked_by` 列表）

---

## 2. 总体设计

**单一数据源（Single Source of Truth）**：`server.service.memory_store` 中的 `AgentState.tasks_context.tasks`。

**双向通路**：
- **冷启动**：前端切换任务时 `GET /api/tasks/{tid}/todos` 全量拉取。
- **热更新**：SSE 流在 todo 列表变化时主动 yield `task_todos_changed` 帧，前端用增量替换（同一份 `list[TodoItem]`，后端每次发完整快照而非 diff）。

为什么发完整快照而非 diff？—— todo 列表通常只有 5~10 条，整体替换实现最简单、不会失同步；diff 需要管理"哪些是新增/删除/修改"状态机，复杂度不值得。

---

## 3. 数据契约

### 3.1 `TodoItem` (后端 → 前端通用结构)

```ts
interface TodoItem {
  id: string                       // AgentScope Task.id（前端展示时前置 "#"）
  subject: string                  // 标题
  description: string              // 详细描述（可能为空字符串）
  state: 'pending' | 'in_progress' | 'completed' | 'deleted'
  owner: string | null             // null 转为不展示
  blocks: string[]                 // 该任务阻塞了谁（id 列表）
  blockedBy: string[]              // 谁阻塞了该任务（id 列表）
  createdAt: string                // ISO 8601 字符串
}
```

### 3.2 REST 端点

#### `GET /api/tasks/{task_id}/todos`

**成功响应**（200）：
```json
{
  "todos": [
    {
      "id": "1",
      "subject": "读取配置文件",
      "description": "加载 .env.example 与 settings.yaml",
      "state": "completed",
      "owner": null,
      "blocks": ["2"],
      "blockedBy": [],
      "createdAt": "2026-09-28T10:00:00+08:00"
    }
  ]
}
```

**错误响应**：
- 404 `{"detail": "task not found"}` —— 任务不存在
- 200 `{"todos": []}` —— 任务存在但 Agent 尚未创建 todo（**不是错误**）

#### 实现要求
- 必须从 `agent_state_store.load(task_id)` 中读取 `tasks_context.tasks`。
- 软删除状态（`state == 'deleted'`）的 todo **仍然返回**（前端可以选择隐藏，但不能因为后端过滤而丢失信息）。
- 客户端可以选 304 `Not Modified` 优化（本版本不做）。

### 3.3 SSE 事件

**事件名**：`task_todos_changed`

**payload**：
```json
{
  "todos": [TodoItem, ...]   // 与 REST 端点同形
}
```

**触发时机**（满足任一即 yield）：
1. Agent 调用 `TaskCreate` 成功 → yield。
2. Agent 调用 `TaskUpdate` 成功 → yield。
3. Agent 调用 `TaskList` / `TaskGet` → 不 yield（只读工具不变化）。
4. **流自然结束时**（`ReplyEndEvent`）→ 总是 yield 一帧（即便内容不变，确保前端在 React 端一定能拿到最新状态）。

**不需要客户端确认**：后端 yield 这一帧是"信号"，前端**不需要回传 ACK**。因为 todo 是 Agent 自己规划用的，前端仅作展示。

### 3.4 事件顺序示例

```
event: thinking_delta    data: ...
event: text_delta        data: ...
event: tool_call_start   data: {"call_id":"c1","tool":"TaskCreate", ...}
event: tool_call_end     data: {"call_id":"c1","status":"success", ...}
event: task_todos_changed data: {"todos":[...]}
event: text_delta        data: ...
event: done              data: ...
```

> **说明**：可在同一帧既 yield `tool_call_end` 又 yield `task_todos_changed`，但通常 AgentScope 内部是顺序派发，逐帧发出更利于调试。

---

## 4. 实现要求

### 4.1 后端（`server/`）

#### 模块改动

| 文件 | 改动 |
|---|---|
| `server/service/events.py` | `EVENT_NAMES` 添加 `task_todos_changed`；新增 `task_todos_changed(todos: list[dict])` 构造函数 |
| `server/service/history.py` | 新增 `serialize_todos(state: AgentState) -> list[TodoItem]` 纯函数（**可单元测试**） |
| `server/main.py` | 新增 `GET /api/tasks/{task_id}/todos` 端点；SSE 翻译器在 `TaskCreate/Update` 成功时 yield `task_todos_changed`；`ReplyEndEvent` 必 yield 一帧 |
| `tests/test_history.py` | 添加 `serialize_todos` 测试（覆盖空/单条/多条/blocks 关系/`deleted` 状态） |
| `tests/test_events.py` | 添加 `task_todos_changed` 帧序列化测试 |

#### 测试要求
- **空 `AgentState`** → `serialize_todos` 返回 `[]`。
- **多 Task 含依赖图** → 返回的列表长度与 `state.tasks_context.tasks` 一致；`blocks` / `blockedBy` 正确序列化。
- **deletes 状态不丢失**：过滤不删数据，前端决定怎么显示。
- **SSE 帧格式**：`task_todos_changed` 帧符合 `event: task_todos_changed\ndata: {...}\n\n`。

### 4.2 前端（`frontend/`）

#### 文件改动

| 文件 | 改动 |
|---|---|
| `src/api/events.ts` | `EVENT_NAMES` 添加 `task_todos_changed`；新增 `TaskTodosChangedData` / `TodoItem` 接口 |
| `src/types/index.ts` | 镜像 `TodoItem` 接口（供组件复用） |
| `src/store/todos.ts` | **新文件** Pinia store：state = `todos`, `loadTodos(taskId)`, `applyFrame(payload)`, `clear()` |
| `src/components/artifacts/ArtifactTabs.vue` | 在现有 4 tab 后增加 `第 5 个 Tab：'todos'`，label = `'待办'` |
| `src/components/artifacts/SidebarRight.vue` | 新增 `TodoPane.vue` 渲染分支 |
| `src/components/artifacts/TodoPane.vue` | **新组件** 渲染 todos 列表（状态图标 + subject + blocked_by 缩略显示） |
| `src/components/chat/SidebarMiddle.vue` | `TaskHeaderBar` 旁增加紧凑徽标：`"3 / 5 待办"`，点击 emit `open-todos-tab` 事件 |
| `src/composables/useChat.ts` | SSE 帧处理：识别 `task_todos_changed` 帧并转发到 todos store；`send()` 成功后用 `todos.loadHistory(taskId)` 预热 |
| `src/components/sidebar/WorkspaceTree.vue` | 切换任务时：`session.reset()` + `session.loadHistory(taskId)` + `todos.loadTodos(taskId)` |
| `tests/store/todos.spec.ts` | **新测试** todos store 行为 |
| `tests/components/TodoPane.spec.ts` | **新测试** 渲染行为 |

#### 组件设计：`TodoPane.vue`

```
┌─────────────────────────────────────┐
│ ⏳ #1  读取配置文件        ✓ done   │
│        加载 .env.example           │
├─────────────────────────────────────┤
│ ⏳ #2  解析配置             ⏳ run    │
│        读取 .yaml                    │
│        blocked by: #1               │
├─────────────────────────────────────┤
│ ☑ #3  创建任务列表        ✓ done   │
├─────────────────────────────────────┤
│ ☐ #4  执行 run()          pending  │
├─────────────────────────────────────┤
│ ☐ #5  生成报告            pending  │
└─────────────────────────────────────┘
```

状态颜色：
- `pending` — 灰色圆圈
- `in_progress` — 蓝色 spinner
- `completed` — 绿色对勾
- `deleted` — 删除线 + 灰色（前端默认隐藏，UI 提供"显示已删除"切换）

#### `TaskHeaderBar.vue` 徽标

```
[任务标题]                [3/5 待办完成]   [重命名] [归档] [清空上下文]
```

点击徽标触发 `useChat` 通过 Pinia 全局事件通知 `SidebarRight` 切换到 `'todos'` tab。

### 4.3 状态一致性保证

| 触发场景 | 状态来源 | 路径 |
|---|---|---|
| 用户切换任务 | `AgentState.tasks_context.tasks` | `GET /todos` → 替换 |
| Agent 完成一轮回复 | SSE 流 + Redis 同步写入 | `task_todos_changed` → 替换 |
| 用户刷新页面 | `AgentState.tasks_context.tasks` | `GET /todos` → 替换 |
| 用户归档/删除任务 | — | 前端 store 调用 `clear()` |

---

## 5. 验收标准

- [ ] **后端**：5 个新单元测试覆盖 `serialize_todos` 边界条件。
- [ ] **后端**：`GET /api/tasks/{tid}/todos` 在 task 存在时返回正确 JSON；任务不存在时返回 404。
- [ ] **后端**：SSE 流在 Agent 调用 `TaskCreate` 后立刻 yield `task_todos_changed` 帧；`ReplyEndEvent` 必发。
- [ ] **前端**：todos store 的 4 个单测全过。
- [ ] **前端**：TodoPane 在空态、单条 pending、单条 completed、多条混合依赖关系四种情形下渲染正确。
- [ ] **前端**：切换任务后，右栏 todo tab 内容跟随切换。
- [ ] **前端**：单条 SSE 帧 `task_todos_changed` 被前端的 `applyFrame` 正确接收并替换。
- [ ] **前后端联调**：运行后端 + 前端后，让 Agent 完成一次 "读取配置 → 解析配置 → 创建任务" 的真实往返，前端能看到 todo 列表从 0 增长到 3、状态从 pending → in_progress → completed。

---

## 6. 不属于本规范

- 阶段二股票工具
- 阶段四多 Agent 模板（多 Agent 共享 todo 列表）
- Todo 编辑/批注功能
- Todo 历史快照（每个 todo 的状态变化轨迹）

---

## Related

- [阶段一后端 spec](2026-09-28-stage1-single-agent-design.md)
- [阶段三前端 spec](2026-09-28-frontend-three-column-workbench.md)
- [本地 LiteLLM 与 v-flash 接入规范](../.learnings/knowledge/litellm-vflash-integration.md)
- [本地 Redis 容器连接信息](../.learnings/knowledge/local-redis-container.md)
- [实施计划 Part 1（后端）](../plans/2026-09-28-part1-backend-agent-plan.md)
- [实施计划 Part 2（前端）](../plans/2026-09-28-part2-frontend-workbench-plan.md)