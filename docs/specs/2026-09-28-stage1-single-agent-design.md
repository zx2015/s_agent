# 阶段一需求文档：单 Agent 内核

> **文档版本**：v1.0
> **创建日期**：2026-09-28
> **状态**：设计已评审通过，待编写实现计划
> **文档位置**：`docs/specs/2026-09-28-stage1-single-agent-design.md`

---

## 一、项目背景与阶段定位

### 1.1 项目总目标

构建一个**前后端分离的通用智能体平台**：

- **前端**：华为 DevUI 团队开源的 **MateChat**（Vue 3 + TypeScript + Vite）
- **后端**：**AgentScope** 框架 + **FastAPI**，对外暴露 SSE 流式接口
- **最终形态**：通用 Agent 底座 → 改造为股票分析智能体

### 1.2 阶段划分

| 阶段 | 目标 | 状态 |
|------|------|------|
| **阶段一（本文档）** | **单 Agent 内核**：系统提示、12 个内置工具、可配置 LLM、四大记忆机制、HITL 权限 | 需求定义中 |
| 阶段二 | 股票分析能力注入（行情工具、计算器业务化、portfolio 管理、节前效应） | 未开始 |
| 阶段三 | MateChat 前端接入（SSE 打字机、会话管理 UI） | 未开始 |
| 阶段四 | 多 Agent 协作（团队工作流、子 Agent 模板） | 未开始 |

### 1.3 阶段一的核心原则

1. **先内核后外延**：只做单 Agent 内核，不引入多 Agent 复杂度。
2. **开箱即用优先**：能用 AgentScope 2.0 原生能力的，不自研。
3. **预留扩展位**：接口设计为阶段二的股票工具、阶段三的前端、阶段四的多 Agent 留好插槽。
4. **实测驱动**：所有技术假设必须经真实环境验证（如 `v-flash` 的 `max_tokens` 陷阱即为实测发现）。

---

## 二、技术选型与环境基线（已实测确认）

### 2.1 框架版本：AgentScope 2.0

**决策**：升级到 AgentScope 2.0，放弃已安装的 1.0.21。

**理由**：需求清单中的 `edit file`、`find file`、`TaskCreate/Get/List/Update` 四件套、上下文卸载机制、HITL 权限引擎，在 1.0.21 中**均缺失或需自研移植**，在 2.0 中**开箱即用**。

**版本能力对比**（2026-09-28 实测）：

| 需求项 | 1.0.21（已装） | 2.0（本地源码） |
|--------|---------------|----------------|
| shell 命令 | ✅ `execute_shell_command` | ✅ `Bash` |
| read file | ⚠️ `view_text_file`（仅文本） | ✅ `Read`（含多模态） |
| write file | ✅ `write_text_file` | ✅ `Write` |
| edit file | ❌ 仅 `insert_text_file`（插入，非精确编辑） | ✅ `Edit` |
| find file | ❌ 无 | ✅ `Glob` + `Grep` |
| Task 四件套 | ❌ 无 | ✅ `tool/_task/` 完整 |
| 计算器 | ❌ 无内置 | ❌ 无内置（需自研） |
| 上下文压缩 | ✅ `CompressionConfig` | ✅ `on_compress_context` 中间件 |
| 上下文注入 | ⚠️ 手动 `memory.add` | ✅ `InjectionConfig` |
| 上下文卸载 | ❌ 无 | ✅ `ToolOffloadMiddleware` |
| 长期记忆 | ✅ `Mem0`/`ReMe*`/`RedisMemory` | ✅ `AgenticMemoryMiddleware` |
| HITL 权限 | ❌ 无 | ✅ `PermissionEngine` |

**安装方式**：

```bash
/media/data/venv/bin/pip install -e /media/data/git/agentscope/src/agentscope
```

**引入的依赖**：Redis（storage 与 message bus）。⚠️ 当前 Redis 服务未启动，需在环境准备阶段解决。

### 2.2 模型接入：本地 LiteLLM `v-flash`

| 项目 | 值 |
|------|-----|
| 服务端点 | `http://127.0.0.1:4000/v1`（OpenAI 兼容协议） |
| 模型名 | `v-flash`（跨 4 平台 7 节点虚拟融合模型，含自动 fallback） |
| 配置文件 | `/media/data/litellm/config/config.yaml` |
| 认证 | Bearer Token，从环境变量读取，**严禁硬编码** |

**已验证的工程约束**：

1. `max_tokens` **必须 ≥ 2048**：`v-flash` 底层为推理模型，先输出 `reasoning_content`；配额定小会吞掉正文，`content` 返回空串。
2. 使用 `client_kwargs={"base_url": ...}`，`client_args` 已废弃。
3. 密钥通过环境变量注入，`.env` 已在 `.gitignore` 中声明忽略。

### 2.3 运行环境基线

- Python：`/media/data/venv`（3.12.14）
- 已装：`fastapi 0.139.0`、`uvicorn 0.43.0`、`redis 6.4.0`、`agentscope 1.0.21`（待升级）
- Node：v24.18.0 + npm 11.16.0（阶段三使用）

---

## 三、功能模块需求（八大模块）

### 模块 A：Agent 身份与系统提示

**A-1 System Prompt 模板**

- 提供默认通用助手 Prompt，须包含：角色定义、能力边界、工具使用准则、输出风格规范。
- 支持三种来源（优先级从高到低）：
  1. 外部文件（`server/prompts/system.md`）
  2. 配置文件内联字符串
  3. 代码内置默认值
- 模板支持变量占位符（如 `{current_time}`、`{workspace_dir}`、`{user_preference}`），渲染后注入。

**A-2 Agent 身份元数据**

- `name`：Agent 名称（默认 `s-agent`）
- `description`：能力描述（用于阶段四多 Agent 路由）
- 元数据随 Agent 实例持久化，会话恢复时一并还原。

**A-3 运行期上下文注入**

- 机制：AgentScope 2.0 `InjectionConfig`
- 注入内容：当前时间、工作区路径、用户偏好、可用工具清单摘要
- **关键要求**：注入必须以**系统提示块**形式附加，**不污染历史消息序列**，且不参与上下文压缩统计。

**验收标准**：

- 修改 `server/prompts/system.md` 后无需改代码即可生效
- 注入的上下文在对话历史中不可见（不占用 Msg 序列）

---

### 模块 B：模型层（可配置 LLM）

**B-1 统一模型抽象**

- 所有模型通过 AgentScope `ChatModelBase` 接入，**不直接对接厂商 SDK**。
- 阶段一默认实现：OpenAI 兼容协议（对接 LiteLLM）。

**B-2 配置优先级**

```
环境变量（S_AGENT_MODEL_NAME / S_AGENT_API_KEY / S_AGENT_BASE_URL）
  ↓ 未设置则
配置文件 server/config.yaml
  ↓ 未设置则
内置默认（v-flash + http://127.0.0.1:4000/v1）
```

**B-3 模型参数管理**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `model_name` | `v-flash` | 模型标识 |
| `base_url` | `http://127.0.0.1:4000/v1` | LiteLLM 端点 |
| `max_tokens` | `4096` | **必须 ≥ 2048**（v-flash 推理模型约束） |
| `temperature` | `0.7` | 采样温度 |
| `stream` | `True` | 流式输出 |

**B-4 运行时热切换**

- 提供 `ModelFactory` 工厂，支持不重启进程切换模型。
- 切换后当前会话的历史消息保持不变。

**B-5 Token 计数**

- 压缩机制依赖精确 token 计数，需选定 `TokenCounterBase` 实现。
- ⚠️ **风险提示**：`v-flash` 是融合模型，不同后端 tokenizer 不一致，需实测确定计数口径（可选启发式估算或指定 tokenizer）。

**验收标准**：

- 通过环境变量覆盖模型配置，无需改代码
- 切换 `S_AGENT_MODEL_NAME` 后新会话生效

---

### 模块 C：内置工具集（12 件套）

**C-1 工具清单**

全部注册到同一个 `Toolkit` 实例：

| # | 工具名 | 实现来源 | 用途 | 来源标注 |
|---|--------|---------|------|---------|
| 1 | shell 命令 | AgentScope `Bash` | 执行受限 shell 命令 | 用户指定 |
| 2 | read file | AgentScope `Read` | 读取文件（含多模态） | 用户指定 |
| 3 | write file | AgentScope `Write` | 写入文件 | 用户指定 |
| 4 | edit file | AgentScope `Edit` | 精确编辑文件 | 用户指定 |
| 5 | find file | AgentScope `Glob` | 文件名模式匹配 | 用户指定 |
| 6 | grep 搜索 | AgentScope `Grep` | 文件内容正则搜索 | ⭐ 补全 |
| 7 | TaskCreate | AgentScope `_task/TaskCreate` | 创建任务 | 用户指定 |
| 8 | TaskGet | AgentScope `_task/TaskGet` | 读取单个任务 | 用户指定 |
| 9 | TaskList | AgentScope `_task/TaskList` | 列出全部任务 | 用户指定 |
| 10 | TaskUpdate | AgentScope `_task/TaskUpdate` | 更新任务状态 | 用户指定 |
| 11 | 计算器 | 自研（移植股票分析项目 `calculator.py`） | 四则运算/百分比/统计 | 用户指定 |
| 12 | AskUser | AgentScope `_builtin/AskUser` | 反问用户澄清需求 | ⭐ 补全 |

**C-2 计算器工具**

- **来源**：移植 `/media/data/git/股票分析/.claude/skills/calculator/calculator.py`
- **能力**：四则运算、百分比变化、盈亏计算、最大回撤、Sharpe 等
- **红线**：计算必须走工具，**严禁 LLM 心算**（继承用户全局强制约定）
- **改造要求**：剔除股票专用逻辑的硬编码，保留通用数学能力，股票语义部分留待阶段二扩展

**C-3 工具安全策略（已拍板）**

| 策略 | 要求 | 状态 |
|------|------|------|
| **工作区沙箱隔离** | 所有文件工具路径参数强制校验，禁止越界访问 `workspace/` 根目录；违规直接拒绝并返回明确错误 | ✅ 阶段一实现 |
| **HITL 权限确认** | `Bash` 工具经 `PermissionEngine`；高危模式（`rm`/`mv`/`chmod`/重定向 `>` 等）必须人工确认，其余放行 | ✅ 阶段一实现 |
| **工具输出截断** | 大输出落盘/截断 | ⏸️ 阶段一暂不实现（留接口） |
| **Token 限额** | 单次调用 token 上限 | ⏸️ 阶段一暂不实现 |

**C-4 工具分组（可选）**

- 利用 AgentScope `ToolGroup` 将工具分为"文件操作组""任务组""通用组"，为阶段二按需激活做准备。

**验收标准**：

- 12 个工具全部可通过 Agent 自然语言指令触发
- 越界路径访问（如 `/etc/passwd`）被拒绝并返回可读错误
- 高危 shell 命令触发 HITL 确认流程
- 计算器精度测试通过（与股票分析项目 `tests.py` 对齐）

---

### 模块 D：记忆管理（四大机制）

**D-1 上下文注入（Context Injection）**

- 机制：AgentScope 2.0 `InjectionConfig`
- 内容：当前时间、工作区路径、用户偏好、工具摘要
- 要求：以系统提示块注入，不污染消息序列（详见模块 A-3）

**D-2 短期工作记忆（Working Memory）**

- 载体：AgentScope `MemoryBase` 实现
- 存储：Redis（跨进程/重启不丢）
- 内容：多轮对话的 `Msg` 序列
- 要求：支持按 session_id 隔离；支持消息标记（`update_messages_mark`）以配合压缩

**D-3 上下文压缩（Context Compression）**

- 机制：`ReActAgent.CompressionConfig` 或 2.0 的 `on_compress_context` 中间件
- 触发条件：token 总数超过阈值 `trigger_threshold`
- 保留策略：最近 `keep_recent`（默认 3）轮消息不压缩
- 摘要结构：任务概览 / 当前状态 / 重要发现 / 下一步 / 需保留上下文（沿用 AgentScope 默认摘要模板）
- 要求：压缩后原消息可追溯（标记而非物理删除）

**D-4 上下文卸载（Context Offload）**

- 机制：AgentScope 2.0 `ToolOffloadMiddleware`
- 触发条件：工具返回结果超过大小阈值
- 行为：大结果落盘到 `workspace/offload/`，上下文内只保留**文件路径指针 + 摘要**
- 要求：Agent 可通过 `read file` 工具按需回读完整内容

**D-5 长期记忆（Long-term Memory）**

- 机制：AgentScope 2.0 `AgenticMemoryMiddleware`
- 存储：Markdown 文件，位于 `workspace/memory/`
- 内容：跨 session 沉淀的用户偏好、重要事实、经验结论
- 要求：按用户/会话隔离；支持 Agent 主动读写；与短期记忆的边界清晰

**验收标准**：

- 注入内容不出现在消息历史
- 长对话（> 50 轮）触发压缩且不丢失任务目标
- 大工具输出（如读取 1MB 文件）被卸载为指针，Agent 能按需回读
- 跨会话重启后，长期记忆内容仍可召回

---

### 模块 E：HITL 权限确认（Human-in-the-Loop）

**E-1 触发场景**

1. 高危工具调用前（shell 危险命令）
2. Agent 主动反问（`AskUser` 工具）

**E-2 交互机制**

```
Agent 发起高危操作
   ↓
PermissionEngine 判定 → RequireUserConfirmEvent
   ↓
SSE 推送给前端 → 用户 确认/拒绝
   ↓
UserConfirmResultEvent 回传 → Agent 继续 ReAct 循环
```

**E-3 判定策略**

- 阶段一实现：**高危模式正则黑名单**
  - 命令：`rm`、`mv`、`chmod`、`chown`、`dd`、`mkfs`、`shutdown`、`reboot`
  - 符号：`>`（重定向）、`|`（管道到危险命令）、`sudo`
- 复杂 ACL 与角色权限**留到阶段二**

**E-4 超时与默认行为**

- 待确认状态需有超时机制（默认拒绝，避免永久挂起）

**验收标准**：

- 执行 `rm` 命令时前端可确认/拒绝，拒绝后 Agent 收到明确反馈并继续
- 普通命令（如 `ls`）不触发确认，流程不中断

---

### 模块 F-0：工作区 Git 化（阶段三 diff 视图前置依赖）

> **背景**：阶段三前端右栏的「文件变更 (Diff)」采用基于 Git 的方案。后端必须在每个工作区/任务目录下初始化 Git 仓库，并按 Agent 执行轮次自动 commit，才能为前端提供完整 diff 历史。

**F-0-1 工作区初始化**

- 每个任务/工作区在创建时，由后端自动执行 `git init` 与首次 commit（初始空状态）。
- `agent_id` 与 `task_id` 作为提交者标识（`user.name` / `user.email` 写入 `.git/config`）。

**F-0-2 自动 commit 策略**

- 触发时机：每次 ReAct 循环结束、每次工具执行（`Write` / `Edit` / `Bash` 涉及文件改动）后。
- commit message 模板：`[agent] <tool_name>: <brief_summary>`（如 `[agent] Write: created index.html`）。
- 提交粒度：阶段一采用「每工具一次 commit」；阶段三可与前端交互节奏细化（用户确认一次 HITL 即 commit）。

**F-0-3 diff API**

- 后端暴露 `GET /api/tasks/{task_id}/git-diff?from=<commit>&to=<HEAD>`，返回 unified diff 文本。
- 同时提供 `GET /api/tasks/{task_id}/git-log` 返回提交历史。

**验收标准**：

- 任务创建后，工作区目录为合法 Git 仓库（`git status` 干净）。
- 任意文件改动后 5 秒内可查到对应 commit。
- 跨会话重启后 commit 历史完整保留。

---

### 模块 F：会话与持久化

**F-1 Session 模型**

- 每个会话独立 `session_id`
- 会话包含：Agent 实例状态、memory 快照、task list 快照、模型配置快照

**F-2 存储后端**

- Redis（AgentScope 2.0 默认路径）
- ⚠️ **前置依赖**：需先启动 Redis 服务（当前未运行）

**F-3 会话生命周期**

| 操作 | 行为 |
|------|------|
| 创建 | 新 session_id，初始化空 memory 与 task list |
| 恢复 | 按 session_id 从 Redis 加载状态，Agent 无缝续聊 |
| 列表 | 查询历史会话（供阶段三前端展示） |
| 删除 | 清理 Redis 中该会话全部数据 |

**验收标准**：

- 服务重启后，用原 session_id 可恢复对话上下文
- 不同 session 之间记忆完全隔离

---

### 模块 G：可观测性与错误兜底

**G-1 事件流与日志**

- 订阅 AgentScope `event` 关键事件：`ReplyStartEvent`、`ReplyEndEvent`、`ModelCall*`、`ToolCall*`、`ToolResult*`
- 落地 JSONL 日志到 `workspace/trace/`，含时间戳、事件类型、载荷摘要
- 要求：日志不含密钥与敏感数据

**G-2 错误兜底**

| 场景 | 处理策略 |
|------|---------|
| 模型调用失败 | 重试 3 次 → 触发 LiteLLM fallback（已有配置）→ 仍失败则返回可读错误 |
| 工具抛异常 | 捕获后以错误结果返回给 Agent，允许其自修复或上报 |
| 会话不存在 | 自动创建新会话或返回明确错误 |
| 中断 | 打通 `UserInterruptEvent` 链路（阶段一不实现主动取消 UI） |

**G-3 阶段一不做的可观测性**

- OpenTelemetry / LangSmith 等外部 tracing（LiteLLM 侧已有 Langfuse，后端暂不集成）

**验收标准**：

- 模型失败时用户看到可读错误而非 500 堆栈
- 每次交互生成完整 trace 文件

---

### 模块 H：可扩展性预留接口

**H-1 MCP 支持（预留，不实现）**

- 依据：`Toolkit.register_mcp_client` 已就绪
- 用途：后续接入外部 MCP Server（浏览器、数据库等）

**H-2 多 Agent 预留（预留，不实现）**

- 依据：AgentScope 2.0 `SubAgentTemplate` 数据结构
- 用途：阶段四团队协作

**H-3 自定义工具注入（预留，实现基础版）**

- 依据：`create_app(extra_agent_tools=...)` 工厂
- 用途：阶段二注入股票行情工具
- 阶段一要求：保证该入口可用且有示例

**H-4 前端契约预留**

- SSE 事件格式需与阶段三 MateChat 前端约定一致
- 事件类型须包含：文本增量、思考增量、工具调用、工具结果、需确认、结束

---

## 四、数据流：一次完整交互

```
用户输入（阶段三：SSE；阶段一：curl/CLI）
   ↓
FastAPI 接口接收 → 解析 session_id
   ↓
ChatService 加载或恢复 session（Redis）
   ↓
InjectionConfig 注入上下文（时间/工作区/偏好）
   ↓
Agent.reply() 触发 ReAct 循环
   ├─ token 超阈值？→ 触发上下文压缩（保留近 3 轮）
   ├─ 模型推理 → ChatResponse（可能含 tool_calls）
   ├─ PermissionEngine 检查
   │     └─ 高危？→ 推 RequireUserConfirmEvent → 等待用户 → UserConfirmResultEvent
   ├─ 工具执行（Toolkit）
   │     └─ 输出超阈值？→ ToolOffloadMiddleware 落盘 → 上下文留指针
   ├─ 工具结果回灌 → 继续循环
   └─ ReplyEndEvent → 退出循环
   ↓
事件流逐条 yield（SSE）
   ↓
session 快照 + trace 日志写回 Redis / workspace
```

---

## 五、验收标准汇总

| 模块 | 核心验收项 |
|------|-----------|
| A 身份提示 | 改 Prompt 文件免改代码生效；注入内容不进消息序列 |
| B 模型层 | 环境变量可覆盖配置；max_tokens ≥ 2048 不返回空 |
| C 工具集 | 12 工具全部可自然语言触发；越界路径被拒；高危命令走 HITL；计算器对齐回归测试 |
| D 记忆 | 注入不污染历史；长对话触发压缩不丢目标；大输出卸载可回读；跨会话长期记忆可召回 |
| E HITL | 高危命令可确认/拒绝；普通命令不打断 |
| F 会话 | 重启后原 session 可恢复；会话间记忆隔离 |
| G 可观测 | 错误可读；每次交互有 trace |
| H 扩展位 | MCP/多 Agent/自定义工具入口存在且可用 |

---

## 六、非目标（阶段一明确不做）

1. MateChat 前端 UI（阶段三）
2. 股票分析业务工具、行情接口、知识库（阶段二）
3. 多 Agent 团队工作流、子 Agent 实例化（阶段四）
4. 复杂 ACL、角色权限、审计日志（阶段二）
5. 工具输出截断、Token 限额（阶段二）
6. OpenTelemetry / LangSmith 外部 tracing（阶段二）
7. 主动取消长任务 UI（阶段二）

---

## 七、风险与依赖

| # | 风险/依赖 | 影响 | 应对 |
|---|----------|------|------|
| 1 | Redis 未启动 | 阻塞会话持久化与 message bus | 环境准备阶段先启动 Redis |
| 2 | 2.0 API 与 1.0.21 不兼容 | 已有 litellm 对接验证代码需重写 | 升级后重跑端到端验证 |
| 3 | `v-flash` 融合模型 tokenizer 不一致 | 压缩阈值计数不准 | 实测选定计数口径，必要时用估算 |
| 4 | 2.0 源码为预览版（submodule main 快照） | 可能有未稳定行为/破坏性变更 | 锁定 commit，记录版本 |
| 5 | HITL 与 SSE 的时序耦合 | 确认流程可能死锁 | 设超时默认拒绝 |
| 6 | 移植计算器工具需去业务耦合 | 移植后可能影响股票阶段 | 保留原文件，新建通用版 |

---

## 八、附录：调研依据

- 本地源码：`/media/data/git/agentscope/src/agentscope/src/agentscope/`
  - 内置工具：`tool/_builtin/`（`_bash.py`、`_read.py`、`_write.py`、`_edit.py`、`_glob.py`、`_grep.py`、`_ask_user.py`）
  - 任务工具：`tool/_task/`（`_create_task.py`、`_get_task.py`、`_list_task.py`、`_update_task.py`）
  - 服务层：`app/_app.py`（`create_app()`）
- 版本能力实测：2026-09-28 于 `/media/data/venv` 执行
- 模型接入实测：2026-09-28 端到端跑通 `v-flash` 流式输出
- 知识沉淀：`.learnings/knowledge/litellm-vflash-integration.md`、`.learnings/knowledge/agentscope-matechat-architecture.md`

---

## Related

- [../../CLAUDE.md](../../CLAUDE.md) — 项目行为准则与技术栈
- [../../TODO.md](../../TODO.md) — 阶段任务清单
- [../../.learnings/knowledge/litellm-vflash-integration.md](../../.learnings/knowledge/litellm-vflash-integration.md) — 模型接入规范