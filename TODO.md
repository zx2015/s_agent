# TODO

> 本文件随代码纳入版本控制。完成事项移至"已完成"并标注日期，严禁直接删除。

## 进行中
- [ ] 用真实 `LITELLM_API_KEY` 跑通一次端到端真实对话（当前环境无可用 key，仅验证了优雅降级路径）— 优先级：高

## 待办
- [ ] 实现四大记忆机制：上下文注入 / 压缩 / 卸载 / 长期记忆 — 优先级：高（阶段一 spec 模块 D）
- [ ] 实现 HITL 权限引擎的精细化规则（当前仅接入 AgentScope 内置 Bash/Write/Edit 危险模式检测的 ASK 行为，未做自定义黑名单/白名单）— 优先级：中（阶段一 spec 模块 E）
- [ ] 移植股票分析项目 calculator.py 的完整功能（当前 `server/tools/calculator.py` 只是一个受限 AST 四则运算求值器，未覆盖股票场景的 Sharpe/回撤等函数）— 优先级：中
- [ ] 跑通"通用 Agent"端到端最小闭环后，再规划股票分析改造 — 优先级：中（依赖真实 key 验证）
- [ ] 评估复用 `/media/data/git/股票分析/scripts/tencent_stock.py` 作为 Toolkit 工具 — 优先级：低（阶段二）
- [ ] 设计 portfolio JSON 读写工具（遵守无引号规范）— 优先级：低（阶段二）
- [ ] 会话历史持久化：当前 `TaskManager` 只持久化工作区/任务元数据（`workspaces/registry.json`），对话历史和 `Agent` 实例随进程重启丢失 — 优先级：中
- [ ] 生产环境的 `workspaces/` 目录清理与磁盘配额策略 — 优先级：低

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

