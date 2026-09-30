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
- [x] 修复"新建工作区"按钮"看起来没反应"的问题，改用内联面板代替 `window.prompt` — 2026-09-30
  - 排查过程（用 Playwright + 真实 Chromium 实测，不是猜的）：`icon-add-directory` 图标本身渲染正常（字体、`::before` 内容都加载正确，截图确认是个文件夹+号图标）；点击后 `window.prompt` 确实弹出、确认后 `POST /api/workspaces` 确实发出、新工作区确实出现在列表里——功能链路是通的。但 `window.prompt`/`window.confirm` 这类原生对话框在真实使用中很容易被浏览器/插件静默拦截或被用户不经意划走，"看起来没反应"更可能是这个原因，而不是代码逻辑错误
  - 用户反馈"新建任务时最好能指定或新建文件夹"——顺势把两个诉求一起解决：`SidebarLeft.vue` 的"+ 新建任务"点击后不再直接创建，而是展开一个内联小面板（任务标题 + 工作区下拉框，下拉框里有"+ 新建文件夹…"选项，选中后出现文件夹名输入框），一次交互同时覆盖"指定已有文件夹"和"新建文件夹"两种诉求；确认按钮在"选择新建文件夹但没填名字"时禁用
  - 移除了独立的、依赖 `window.prompt` 的"新建工作区"按钮（`icon-add-directory`），其能力已经并入上面的面板；`WorkspaceTree.vue` 每个工作区分组上那个悬停可见的"+"（在已展开的某个具体工作区里快速建任务）保留不变，两者不冲突
  - 真实端到端验证（Playwright 操作真实 Chromium，非单元测试 mock）：打开面板 → 填标题 → 下拉选"+新建文件夹" → 填新文件夹名 → 确认按钮从禁用变可点 → 点击 → 面板关闭 → 侧边栏里新文件夹和任务都正确出现
  - 前端测试：重写 `tests/components/SidebarLeft.spec.ts`（6 个，覆盖面板开关/选已有工作区建任务/自定义标题/新建文件夹+建任务两步请求/确认按钮禁用态/取消不发请求）；共 103 个测试全部通过，typecheck 干净，prod build 验证通过
- [x] 新增"删除工作区"功能 + 文件夹选择器改为可视化文件浏览风格 — 2026-09-30
  - 明确设计前提：本项目里的"工作区/文件夹"是后端的逻辑分组（`registry.json` 里的一条记录 + 磁盘上一个目录），不是用户桌面上的真实路径，所以"文件浏览器窗口选文件夹"不能也不应该做成调用 OS 原生文件对话框——而是在应用内做一个视觉上是文件浏览器（文件夹图标 + 可点击行 + 选中态高亮）、语义上仍是"选/建一个逻辑工作区"的选择器
  - 后端：`TaskManager.delete_workspace(workspace_id)` 复用已有的 `delete_task()` 逐个清理该工作区下的每个任务（元数据/内存 Agent/Redis 状态/磁盘目录一样不少），再移除工作区记录本身并落盘；`DELETE /api/workspaces/{workspace_id}` 路由，工作区不存在返回 404
  - 前端删除入口：`WorkspaceTree.vue` 每个工作区分组 header 悬停显示 `McDeleteIcon` 删除按钮（`@click.stop` 避免连带触发分组折叠/选中），点击弹 `window.confirm`，文案里带上该工作区当前任务数（前端本地就有这份数据，不必额外请求后端），确认后调用新增的 `workspaceStore.deleteWorkspaceRemote()`；若被删工作区里含有当前打开的任务，同步 `sessionStore.reset()`
  - 文件夹选择器重做：`SidebarLeft.vue` 创建任务面板里原来的原生 `<select>` 换成 `.folder-picker`——一个可滚动的行列表，每行是 `icon-folder` 图标 + 工作区名，点击行即选中（高亮），列表末尾"新建文件夹…"行用 `icon-folder-new` 图标，选中后展开新文件夹名输入框（沿用原逻辑）；用 Playwright 截图确认了视觉效果（文件夹图标 + 选中高亮清晰可辨）
  - 真实端到端验证：curl 直接建工作区+任务→ `DELETE /api/workspaces/{id}` → 确认工作区和其任务都从 `GET /api/workspaces` 里消失；Playwright 驱动真实 Chromium 走完整链路（面板建新文件夹+任务 → 侧边栏可见 → 悬停分组显示删除按钮 → 点击确认对话框 → 工作区连带任务从页面消失）
  - 新增/更新测试：后端 `tests/test_task_manager.py`（+4 个，覆盖未知 id 返回 False / 级联删除任务与目录 / 不影响其他工作区 / 空工作区可正常删除）；前端 `store/workspaces.ts` 新增 `deleteWorkspaceRemote`（`tests/store/workspaces.spec.ts` +3 个）、`WorkspaceTree.vue` 新增删除按钮（`tests/components/WorkspaceTree.spec.ts` +3 个）、`SidebarLeft.vue` 文件夹选择器改版相应更新已有测试并新增 1 个专门验证行列表渲染/选中态的用例；后端测试 30→34，前端测试 103→110，typecheck 与 prod build 均验证通过
