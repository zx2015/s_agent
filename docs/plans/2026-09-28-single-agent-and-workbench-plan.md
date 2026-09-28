# s_agent 单 Agent 内核 + 前端三栏工作台 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个基于 AgentScope 2.0.8 + LiteLLM `v-flash` 的单 Agent 内核（FastAPI 后端），并搭建 Vue3 + MateChat 的「左-中-右」三栏工作台前端，跑通通用 Agent 的端到端 SSE 流式交互。

**Architecture:** 后端采用分层架构 — 配置层（`server/config.py`）、模型层（`server/llm/`）、Agent 装配层（`server/agent/`）、工具注册层（`server/tools/`）、记忆层（`server/memory/`）、服务层（`server/service/` FastAPI 路由）。前端基于 Vue 3 + TypeScript + Vite，状态管理用 Pinia，UI 用 MateChat + splitpanes，REST 调用通过 mock 服务并行开发。两者通过纯 SSE (`text/event-stream`) 解耦，可独立开发与测试。

**Tech Stack:**
- **后端**: Python 3.12.14 (venv at `/media/data/venv`)、FastAPI 0.139、Uvicorn 0.43、AgentScope 2.0.8（editable 安装）、Redis 7.4.3（宿主机端口 6380）、LiteLLM `v-flash`（`http://127.0.0.1:4000/v1`）
- **前端**: Vue 3、TypeScript、Vite 5、`@matechat/core`、`vue-devui`、`@devui-design/icons`、`splitpanes`、Pinia、`markdown-it`、`highlight.js`、`vue-diff`
- **持久化**: Redis（会话/任务/git 元数据）、JSON 文件（产品产物）
- **测试**: pytest + httpx（后端）、Vitest（前端）

---

## 关键前置条件 (One-time Setup)

执行计划前**确认以下条件**（每项已被实测验证）：

| 条件 | 验证命令 | 期望 |
|------|---------|------|
| venv 中 AgentScope 2.0.8 已 editable 安装 | `/media/data/venv/bin/pip show agentscope \| grep -E "Version\|Editable"` | `Version: 2.0.8`、`Editable project location: /media/data/git/agentscope/src/agentscope` |
| LiteLLM 可达 | `curl -s -m 5 http://127.0.0.1:4000/v1/models` | 返回 JSON 含 `v-flash` 模型 |
| Redis 在 6380 端口可连 | `/media/data/venv/bin/python -c "import redis; print(redis.Redis(port=6380).ping())"` | 输出 `True` |
| git 已装 | `git --version` | 输出 git 版本号 |

---

## 计划目录

| 文件 | 内容 | 任务数 |
|------|------|--------|
| **本文档** | 总体目标、文件结构、Part 1/2 索引、Common Setup | — |
| [Part 1 - 后端单 Agent 内核](2026-09-28-part1-backend-agent-plan.md) | 后端配置 → 模型 → Agent → 工具 → 记忆 → 服务层 → 端到端 E2E | 14 任务 |
| [Part 2 - 前端三栏工作台](2026-09-28-part2-frontend-workbench-plan.md) | Vite 工程 → Pinia → MateChat → 左/中/右栏 → SSE 接入 → Mock | 12 任务 |

---

## 文件结构（目标态）

```
s_agent/
├── server/                                # 后端工程 (Python)
│   ├── __init__.py                        # 包初始化
│   ├── config.py                          # 环境变量驱动的统一配置
│   ├── llm/                               # 模型层（2.0 OpenAI 兼容接入）
│   │   ├── __init__.py
│   │   ├── credential.py                  # OpenAICredential 工厂
│   │   └── model.py                       # OpenAIChatModel 工厂（Parameters 实例）
│   ├── agent/                             # Agent 装配层
│   │   ├── __init__.py
│   │   ├── core.py                        # 通用单 Agent 工厂（create_agent）
│   │   └── system_prompt.py               # 默认 system prompt 加载器
│   ├── tools/                             # 工具注册层
│   │   ├── __init__.py
│   │   ├── registry.py                    # 12 工具注册器（Toolkit 装配）
│   │   ├── calculator.py                  # 移植自股票分析项目 calculator skill
│   │   └── builtin.py                     # 12 内置工具引入/创建
│   ├── memory/                            # 记忆层
│   │   ├── __init__.py
│   │   ├── compression.py                 # CompressionConfig 装配
│   │   ├── injection.py                   # InjectionConfig 工厂
│   │   └── long_term.py                   # AgenticMemoryMiddleware 工厂
│   ├── service/                           # FastAPI 路由与 SSE 服务
│   │   ├── __init__.py
│   │   ├── app.py                         # create_app() 主入口
│   │   ├── chat.py                        # POST /api/chat 路由（fire-and-forget）
│   │   ├── stream.py                      # GET /api/sessions/{sid}/stream SSE 路由
│   │   ├── tasks.py                       # 任务/工作区 CRUD REST
│   │   ├── artifacts.py                   # GET /api/tasks/{tid}/artifacts/preview/* 受控端点
│   │   ├── git_diff.py                    # GET /api/tasks/{tid}/git-diff
│   │   ├── confirm.py                     # POST /api/tasks/{tid}/confirm（HITL 回传）
│   │   └── events.py                      # SSE 事件格式定义（向后兼容阶段三前端）
│   ├── workspace/                         # 工作区 + git 化管理
│   │   ├── __init__.py
│   │   └── git_init.py                    # git init + 自动 commit 钩子
│   └── prompts/                           # system prompt 模板
│       └── system.md                      # 默认通用助手 prompt（可被外部覆盖）
├── tests/                                 # 后端测试 (pytest)
│   ├── __init__.py
│   ├── conftest.py                        # 共享 fixtures (fake v-flash)
│   ├── test_config.py                     # 配置加载
│   ├── test_llm.py                        # 模型与 credential
│   ├── test_agent.py                      # Agent 工厂
│   ├── test_tools_calculator.py           # 计算器精度回归
│   ├── test_memory.py                     # 记忆机制
│   ├── test_service_chat.py               # /api/chat 路由
│   ├── test_service_stream.py             # SSE 流式事件
│   ├── test_service_artifacts.py          # 受控文件端点
│   └── test_e2e.py                        # 端到端（mock 模型）
├── frontend/                              # 前端工程 (Vue3)
│   ├── package.json
│   ├── vite.config.ts                     # 含 /api → http://localhost:8000 代理
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.ts                        # createApp + MateChat
│   │   ├── App.vue                        # 三栏根布局
│   │   ├── store/                         # Pinia stores
│   │   │   ├── workspaces.ts              # 工作区 + 任务树
│   │   │   ├── session.ts                 # 当前会话（消息流 + 任务状态）
│   │   │   └── settings.ts                # 用户设置（模型、HITL 严格度）
│   │   ├── api/                           # API 封装
│   │   │   ├── client.ts                  # fetch wrapper + SSE EventSource
│   │   │   ├── workspaces.ts
│   │   │   ├── tasks.ts
│   │   │   ├── artifacts.ts
│   │   │   └── events.ts                  # SSE 事件类型定义
│   │   ├── mock/                          # Mock 服务（并行开发）
│   │   │   └── sse-server.ts              # 模拟真实打字机/工具/产物事件
│   │   ├── views/
│   │   │   └── WorkbenchView.vue          # 三栏主页面
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── ThreeColumnLayout.vue  # splitpanes 三栏 + 折叠
│   │   │   │   └── TopBar.vue
│   │   │   ├── sidebar/
│   │   │   │   ├── SidebarLeft.vue        # 左栏：搜索 + 工作区树 + 头像
│   │   │   │   ├── WorkspaceTree.vue
│   │   │   │   └── SettingsDrawer.vue
│   │   │   ├── chat/
│   │   │   │   ├── SidebarMiddle.vue      # 中栏：对话流
│   │   │   │   ├── MessageList.vue
│   │   │   │   ├── UserMessage.vue
│   │   │   │   ├── AssistantMessage.vue   # McBubble 包装
│   │   │   │   ├── ThinkingBlock.vue
│   │   │   │   ├── ToolCallCard.vue       # Bash/File/Task 工具卡片
│   │   │   │   ├── HitlConfirmCard.vue
│   │   │   │   ├── TaskHeaderBar.vue
│   │   │   │   └── ChatInput.vue          # McInput 包装
│   │   │   └── artifacts/
│   │   │       ├── SidebarRight.vue       # 右栏：4 个 Tab
│   │   │       ├── ArtifactTabs.vue
│   │   │       ├── PreviewPane.vue       # iframe + Markdown 渲染
│   │   │       ├── FileTreePane.vue
│   │   │       ├── DiffPane.vue           # vue-diff
│   │   │       └── DownloadPane.vue
│   │   ├── types/                         # TS 类型
│   │   │   └── index.ts
│   │   └── styles/
│   │       └── global.css
│   └── tests/                             # 前端测试 (Vitest)
│       ├── store/
│       ├── components/
│       └── api/
├── docs/                                  # 文档
│   ├── specs/
│   │   ├── 2026-09-28-stage1-single-agent-design.md
│   │   └── 2026-09-28-frontend-three-column-workbench.md
│   └── plans/
│       ├── 2026-09-28-single-agent-and-workbench-plan.md   # 本文
│       ├── 2026-09-28-part1-backend-agent-plan.md
│       └── 2026-09-28-part2-frontend-workbench-plan.md
└── ... (其余 .learnings/、TODO.md、CLAUDE.md 等基础设施不变)
```

---

## 执行策略

### 推荐执行顺序

```
Phase 1: Common Setup（一次性）
   ↓
Phase 2: 后端内核 (Part 1) ┐
                          ├─ 可并行（Mock 隔离）
Phase 2: 前端骨架 (Part 2) ┘
   ↓
Phase 3: 联调（前端 vite proxy 指向真实后端）
```

### 关键解耦点

- **后端**：`POST /api/chat` 与 `GET /api/sessions/{sid}/stream` 的 SSE 事件契约由 [`docs/specs/2026-09-28-frontend-three-column-workbench.md` §3.2](../../specs/2026-09-28-frontend-three-column-workbench.md) 锁定；后端实现必须**严格符合**。
- **前端**：在 `src/mock/sse-server.ts` 提供与该契约一致的 Mock 数据，开发者不依赖后端即可跑通 UI 与交互。
- **联调**：前端 `vite.config.ts` 中 `server.proxy['/api'] = 'http://localhost:8000'`，实现开发期一键切换 mock/真实。

---

## 通用约定（贯穿所有任务）

### 代码风格
- **后端**：PEP 8，函数/类 docstring 必须完整（Google style），所有 Pydantic 模型显式声明类型。
- **前端**：ESLint + Prettier，Vue 3 `<script setup lang="ts">`，组件文件名 PascalCase。

### 提交规范
Conventional Commits（参考 AgentScope 上游规范）：
```
feat: <scope>: <description>
fix: <scope>: <description>
test: <scope>: <description>
docs: <scope>: <description>
refactor: <scope>: <description>
chore: <scope>: <description>
```

`<scope>` 例：`backend`、`frontend`、`config`、`tools`、`service`、`memory`、`workspace`。

每个 Task 的 Step 5/末尾有 `git commit` 操作，**严禁**将多个任务合并提交。

### 测试策略
- **后端**：所有模块有对应 `tests/test_*.py`，pytest + httpx。先写测试 → 看到失败 → 实现 → 看到通过 → 提交。
- **前端**：组件用 Vitest + `@vue/test-utils`，store 用 Pinia testing。事件契约（`api/events.ts`）必须 100% 与后端对齐。

### 安全约束
- 所有密钥、令牌通过环境变量注入（**严禁硬编码**到代码或注释中）。
- 所有 Python 文件顶部 `os.getenv()` 默认值可以是空字符串或 `None`，**严禁**填入真实凭据。
- 工作区路径校验：所有文件工具必须限制在 `workspace/` 根目录内，越界返回明确错误。

---

## 阶段产物（每个 Task 完成后）

每完成一个 Task，必须满足：
1. ✅ 该 Task 内的所有 checkbox 已勾选
2. ✅ 测试全部通过（对应 `test_*.py` 或 Vitest）
3. ✅ 已 `git commit` 且提交信息规范
4. ✅ 若为前端任务，新增/修改文件已在前端浏览器或 mock 模式下视觉验证

---

## 相关

- [Part 1 - 后端单 Agent 内核](2026-09-28-part1-backend-agent-plan.md) — 14 个任务，从配置到 E2E
- [Part 2 - 前端三栏工作台](2026-09-28-part2-frontend-workbench-plan.md) — 12 个任务，从 Vite 到 SSE 接入
- [2026-09-28-stage1-single-agent-design.md](../../specs/2026-09-28-stage1-single-agent-design.md) — 阶段一后端内核 Spec
- [2026-09-28-frontend-three-column-workbench.md](../../specs/2026-09-28-frontend-three-column-workbench.md) — 阶段三前端工作台 Spec