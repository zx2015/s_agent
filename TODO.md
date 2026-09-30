# TODO

> 本文件随代码纳入版本控制。完成事项移至"已完成"并标注日期，严禁直接删除。

## 进行中
- （无）

## 待办
- [ ] 实现"卸载"（offload）与"长期记忆"（跨任务 RAG 知识库）—— 四大记忆机制里剩下的两项；"上下文注入"与"压缩"其实是 AgentScope 默认就自带的（`InjectionConfig`/`ContextConfig` 未做任何定制，走的是框架默认值），已在会话历史持久化那条里连带记录，不再单列 — 优先级：中（阶段一 spec 模块 D）
- [ ] 校准 `OpenAIChatModel(context_size=...)`：目前用的是 AgentScope 默认值 128000 token，未针对 `v-flash` 实际上下文窗口校正，影响自动压缩的触发时机 — 优先级：中
- [ ] 实现 HITL 权限引擎的精细化规则（当前仅接入 AgentScope 内置 Bash/Write/Edit 危险模式检测的 ASK 行为，未做自定义黑名单/白名单）— 优先级：中（阶段一 spec 模块 E）
- [ ] 移植股票分析项目 calculator.py 的完整功能（当前 `server/tools/calculator.py` 只是一个受限 AST 四则运算求值器，未覆盖股票场景的 Sharpe/回撤等函数）— 优先级：中
- [ ] 跑通"通用 Agent"端到端最小闭环后，再规划股票分析改造 — 优先级：中（依赖真实 key 验证）
- [ ] 评估复用 `/media/data/git/股票分析/scripts/tencent_stock.py` 作为 Toolkit 工具 — 优先级：低（阶段二）
- [ ] 设计 portfolio JSON 读写工具（遵守无引号规范）— 优先级：低（阶段二）
- [ ] 生产环境的 `workspaces/` 目录清理与磁盘配额策略 — 优先级：低
- [ ] 修复"归档"按钮：`TaskHeaderBar.vue` 的归档目前只调用 `workspaceStore.archiveTask`，只在前端内存里隐藏任务，从没调用过后端——刷新页面（重新 `fetchWorkspaces`）后归档过的任务会原样出现。做"删除对话"功能时顺带发现，未修复（不在本次需求范围内）— 优先级：低

## 已完成
- [x] 初始化项目基础设施（.learnings / .gitignore / TODO.md / CLAUDE.md）— 2026-09-28
- [x] 选定模型 provider：本机 LiteLLM 的 `v-flash`，并完成端到端流式验证 — 2026-09-28
- [x] 确认运行环境：venv 为 Python 3.12.14，已装 agentscope 1.0.21 / fastapi 0.139 / uvicorn 0.43 — 2026-09-28
- [x] 编写阶段一后端单 Agent 内核 spec（八大模块 + 验收标准）— 2026-09-28
- [x] 编写阶段三前端三栏工作台 spec（含 SSE 契约 + 并行开发机制）— 2026-09-28
- [x] 拍板关键决策：框架升级 2.0 / 安全边界 HITL+沙箱 / 计算器复用 / 前端双层架构+纯SSE+iframe文件服务+git diff / 前后端并行 — 2026-09-28
- [x] 确认本地 Redis 容器：宿主机端口 6380（容器内 6379），无密码，Redis 7.4.3，healthy — 2026-09-28
- [x] 升级 AgentScope 到 2.0.8：以 editable 模式安装本地源码（含 `[service,storage-redis]` extras）— 2026-09-28
- [x] 重跑 AgentScope 2.0.8 + LiteLLM `v-flash` 端到端验证：流式输出与完整事件序列均通过，摸清 2.0 的 6 个 API 破坏性变更 — 2026-09-28
- [x] 制定实施计划：主计划 + Part 1（后端 14 任务 TDD）+ Part 2（前端 12 任务 TDD），均含完整代码与验证命令 — 2026-09-28
- [x] 完成前端 Part 2（12 任务）：SSE 契约/API 客户端/Mock/3 个 Pinia stores/3 栏布局/共 29 个源文件 + 12 个测试文件，87 tests passed，typecheck 干净，dev 与 prod build 均通过 — 2026-09-29
  - 含 4 处计划外适配：splitpanes v4 resize 载荷真实 API / lightningcss errorRecovery 兼容 DevUI / erasableSyntaxOnly 下构造函数不能有参数属性 / `<think>` 标签跨 chunk 的状态机（避免闭合标签泄漏到答案）
- [x] 搭建后端骨架：`server/` 包（config / agent / tools / service / schemas / main.py），基于 AgentScope 2.0.8 `Agent` + FastAPI，跑通 `POST /api/chat` SSE 流式，含 10 个 pytest 单测全绿 — 2026-09-30
  - 工具注册：Bash/Read/Write/Edit/Glob/Grep/AskUser/TaskCreate/TaskGet/TaskList/TaskUpdate（AgentScope 内置）+ 自研 calculate（受限 AST 求值器，替代心算）
  - `server/service/events.py`：AgentScope 事件 → SSE 帧翻译器，逐字段对齐 `frontend/src/api/events.ts`
  - `server/service/task_manager.py`：工作区/任务注册表（JSON 持久化）+ 每任务独立 `Agent`/git 仓库 + `asyncio.Future` 实现的 HITL 确认桥接（`RequireUserConfirmEvent` ⇄ `UserConfirmResultEvent`）
  - REST 端点：`/api/workspaces`、`/api/tasks`（POST/PATCH）、`/api/tasks/{id}/confirm`、`/api/tasks/{id}/files`、`/api/tasks/{id}/git-diff`、`/api/tasks/{id}/artifacts/preview/*`、`/api/tasks/{id}/artifacts/download`
  - 产物探测：轮次结束时按 mtime 扫描工作区新文件，生成 `artifact_created` 帧（非依赖模型显式声明）
- [x] 前端接入 MateChat 官方组件：`ChatInput.vue` 改用 `McInput`（loading/cancel 语义映射停止生成），`UserMessage.vue`/`AssistantMessage.vue` 改用 `McBubble`；`vite.config.ts` 新增对 `@matechat/core` 子包目录导入的自动别名（解决其 `module`-only、无 `exports` map 在 vitest 下的解析问题）— 2026-09-30
- [x] 前后端联调收尾：`store/workspaces.ts` 新增 `fetchWorkspaces`/`createTaskRemote` 走真实 REST；`App.vue` 挂载时拉取工作区；HITL 确认卡片改为通过 `useChat().confirmToolCall` 调用 `POST /api/tasks/{id}/confirm`（此前只清本地状态，未回传后端）— 2026-09-30
  - 前端 88 tests passed（新增 1 个），typecheck 干净，dev server 与 prod build 均验证通过
  - 后端 10 tests passed（calculator 4 个 + events 翻译器 6 个）；`/api/chat` 在无 `LITELLM_API_KEY` 时验证了优雅降级（SSE 内返回错误帧而非 500）
- [x] 用真实 `LITELLM_API_KEY` 跑通端到端真实对话，并修复两个真实 bug — 2026-09-30
  - calculate 工具默认会弹 HITL 确认（AgentScope 对无显式权限声明的 `FunctionTool` 安全默认值），已显式声明 `PermissionDecision(ALLOW)`
  - calculate 返回 `ToolResponse`（错误类型）导致 `FunctionTool` 适配器把整个对象 repr 塞进结果文本；改为直接返回 `str`
  - 修复"发消息没反应"：`useChat.send()` 之前要求先手动选中任务，无任务时静默返回；新增 `ensureActiveTask()` 自动建任务
  - 字体可读性：`#86909c`/`#c9cdd4`（对比度 <3:1）统一替换为 `--color-text-muted: #57606a`（约 5:1）
- [x] 更彻底地接入 MateChat：布局、Markdown 渲染、任务列表、空状态引导均改用官方组件而非仅气泡/输入框 — 2026-09-30
  - `SidebarMiddle.vue`：`McLayout`/`McLayoutHeader`/`McLayoutContent`/`McLayoutSender`，`McLayoutContent` 内置的自动滚底（含用户上滑暂停 + 跳转箭头）替换了手写的 `watch()+scrollTop` 逻辑
  - `SidebarLeft.vue`/`SidebarRight.vue`：`McLayoutAside`（覆盖其默认 `flex-direction:row`，因为我们是垂直侧栏，已加注释说明）
  - `AssistantMessage.vue`：`McMarkdownCard` 替换手写 `markdown-it`+`highlight.js`（两个包已从 `package.json` 移除）；新增 `McToolbar` 复制按钮（`McCopyIcon` 自带剪贴板写入）
  - `WorkspaceTree.vue`：`McList`（`variant="transparent"`，`#item` 插槽保留原有状态点/产物徽标）承载每个工作区分组内的任务；分组折叠本身没有对应的 MateChat 组件，仍是自定义的
  - `App.vue`：`McHeader`（`#operationArea` 插槽放当前任务名）
  - `MessageList.vue` 空状态：`McIntroduction` + `McPrompt` 建议提示词，点击直接调用 `useChat().send()` 运行
  - 新增 `frontend/tests/setup.ts` 全局 stub `ResizeObserver`（jsdom 未实现，`McLayoutContent` 无条件构造它）
  - 前端 89 tests passed，typecheck 干净，prod build 验证通过
- [x] System Prompt 扩展 + 会话历史持久化（Redis）— 2026-09-30
  - `server/agent/core.py`：System Prompt 新增 GFM 渲染说明 / 权限模式与拒绝调用处理 / `<system-reminder>` 与工具中间件来源说明 / 动态检测的 `<env>` 环境信息块（工作目录、是否 git 仓库、平台、真实 shell——发现 AgentScope 的 Bash 工具其实是用 `/bin/sh -c` 而非字面 bash 执行命令，通过解析 `/bin/sh` 符号链接目标如实上报、内核版本、模型名）
  - 调研确认：AgentScope 官方在线文档（`doc.agentscope.io`）描述的 `StateModule`/`agent.state_dict()`/`agentscope.session.JSONSession` 与本地实际安装的 2.0.8 源码完全对不上（已验证 `agentscope.session` 模块根本不存在）；改为直接读本地已安装源码 + 实测验证，确认真正的机制是 `agentscope.state.AgentState`（纯 pydantic BaseModel）+ `Agent(state=...)` 构造参数，且这正是 AgentScope 自己的 Redis/SQL 存储后端（`agentscope.app.storage`）内部使用的同一持久化单元
  - 新增 `server/service/memory_store.py`：`AgentStateStore`，用已有的本地 Redis 容器（端口 6380）保存/加载每个任务的 `AgentState`，key 为 `s_agent:agent_state:{task_id}`，TTL 30 天（可配），加载校验失败时优雅降级为全新会话而非报错
  - `task_manager.get_or_create_agent()` 冷启动时先尝试从 Redis 加载；只在 `ReplyEndEvent`（整轮真正结束）时保存，不在工具调用等待 HITL 确认期间保存——避免恢复出"工具调用发出了但没有结果"的不一致状态（AgentScope 会对这种状态直接抛错）
  - 真实验证：发消息让模型记住一个数字 → `kill -9` 粗暴杀死后端进程（非优雅关闭）→ 全新进程启动，内存缓存完全为空 → 直接问该任务"之前的数字是多少" → 正确答对，证明历史确实从 Redis 恢复
  - `save_agent_state` 做成"尽力而为"：持久化失败只记日志不抛出（此时该轮回复的 SSE 帧、含 `done`，已经发给前端了，抛出去只会让 `main.py` 外层 except 再发一个多余的 `done`/错误帧）；`get_or_create_agent` 的加载失败则保留原样往外抛——历史读取失败应该让用户看到明确报错，而不是悄悄当作"没有历史"
  - 新增 `tests/test_system_prompt.py`（6 个）+ `tests/test_memory_store.py`（5 个，真实连接本地 Redis）+ `tests/test_task_manager.py`（2 个）；后端测试从 17 增至 24 全部通过

- [x] 新增"删除对话"功能（真正的后端删除，非仅前端隐藏）— 2026-09-30
  - 后端：`DELETE /api/tasks/{task_id}`，`TaskManager.delete_task()` 一次性清理任务元数据（含持久化到 `registry.json`）、内存里缓存的 `Agent`、Redis 里的 `AgentState`、磁盘上的整个工作区目录；Redis 删除失败按"尽力而为"处理（记日志不阻断，与 `save_agent_state` 同一策略），任务不存在时返回 `False` 交给路由层转 404
  - 前端：`ApiClient.delete()`、`workspaceStore.deleteTaskRemote()`；`WorkspaceTree.vue` 每个任务行 hover 时显示删除按钮，点击弹 `window.confirm` 二次确认，删的是当前打开的任务时同步清空中间栏的 `sessionStore`
  - 真实端到端验证：建任务 → 对话 → 确认工作区目录/Redis key/任务列表三处都存在 → 调用删除 → 三处全部清除；重复删除同一 task 正确返回 404
  - 顺带发现但本次不修：「归档」按钮目前只在前端本地隐藏任务，从未调用后端，刷新页面会复活（见「待办」）
  - 新增/更新测试：后端 `tests/test_task_manager.py`（+3 个）；前端 `tests/api/client.spec.ts`（+1 个）、`tests/components/WorkspaceTree.spec.ts`（+4 个）；后端测试 24→27，前端测试 89→94，全部通过
- [x] 删除按钮改用图标 + 支持指定/新建工作区 — 2026-09-30
  - 删除按钮从纯文本"✕"改为 `McDeleteIcon`（`@matechat/core/Toolbar`），进一步减少手写图标、复用 MateChat 组件
  - 后端新增 `POST /api/workspaces`（`TaskManager.create_workspace(name)`），生成独立于显示名的 workspace id，起始不带任何任务——区别于 `create_task` 隐式建工作区那条路径（那条路径把 workspace_id 本身当显示名用，对"default"合适，对用户输入的名字不合适）
  - 前端：`WorkspaceTree.vue` 每个工作区分组 header 新增"+"按钮（`icon-add`），点击直接在**该工作区**里建任务并选中——这就是"如何指定工作区"的答案：点哪个分组的"+"，任务就归到哪个工作区；`SidebarLeft.vue` 顶部新增"新建工作区"按钮（`icon-add-directory`），`window.prompt` 输入名称后调用后端创建
  - 原来顶部"+ 新建任务"保持不变（仍是快速创建到第一个工作区的默认行为），新增的都是叠加能力，不影响老路径
  - 真实端到端验证：`POST /api/workspaces` 建"我的新项目" → 在该工作区 id 下建任务 → `GET /api/workspaces` 确认分组正确、任务归属正确
  - 新增/更新测试：后端 `tests/test_task_manager.py`（+3 个，覆盖 `create_workspace` 的 id 生成、空任务列表、可正常接收任务）；前端 `tests/store/workspaces.spec.ts`（+1）、`tests/components/WorkspaceTree.spec.ts`（+2）、新增 `tests/components/SidebarLeft.spec.ts`（3 个）；后端测试 27→30，前端测试 94→100，typecheck 与 prod build 均验证通过
