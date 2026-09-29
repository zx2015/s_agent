# TODO

> 本文件随代码纳入版本控制。完成事项移至"已完成"并标注日期，严禁直接删除。

## 进行中
- [ ] 编写 `server/config.py`：从环境变量读取 `LITELLM_API_KEY` 与 `S_AGENT_REDIS_PORT=6380`，固化 base_url 与模型名 `v-flash` — 优先级：高
- [ ] 搭建后端骨架：基于 AgentScope 2.0.8 统一 `Agent` 类 + FastAPI，跑通 `POST /api/chat` SSE 流式 — 来源：阶段一 spec 模块 B/C/D
- [ ] 搭建前端骨架：Vue3 + Vite + `@matechat/core` + `splitpanes` 三栏布局，先用 mock SSE 跑通 UI — 来源：阶段三 spec（与后端并行）

## 待办
- [ ] 实现 12 个内置工具注册（Bash/Read/Write/Edit/Glob/Grep/Task×4/计算器/AskUser）— 优先级：高（阶段一 spec 模块 C）
- [ ] 实现四大记忆机制：上下文注入 / 压缩 / 卸载 / 长期记忆 — 优先级：高（阶段一 spec 模块 D）
- [ ] 实现工作区 Git 化 + git-diff API（前端 diff 视图前置）— 优先级：高（阶段一 spec 模块 F-0）
- [ ] 实现 HITL 权限引擎（高危命令黑名单 + 确认流）— 优先级：中（阶段一 spec 模块 E）
- [ ] 移植股票分析项目 calculator.py 为通用计算器工具 — 优先级：中
- [ ] 跑通"通用 Agent"端到端最小闭环后，再规划股票分析改造 — 优先级：中（依赖通用 Agent 先工作）
- [ ] 评估复用 `/media/data/git/股票分析/scripts/tencent_stock.py` 作为 Toolkit 工具 — 优先级：低（阶段二）
- [ ] 设计 portfolio JSON 读写工具（遵守无引号规范）— 优先级：低（阶段二）

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
