# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位与演进路线

本项目是一个**前后端分离的通用智能体（Agent）平台**，前期跑通基础对话闭环，后期改造演进为**股票分析智能体**：
- **前端**：基于华为 DevUI 团队开源的 **MateChat**（Vue 3 + TypeScript + Vite）。
- **后端**：基于 **AgentScope** 框架构建智能体核心，使用 **FastAPI** 对外暴露 SSE（Server-Sent Events）流式接口。
- **演进原则**：**先通用后专用**。必须在通用 Agent 的 SSE 流式一问一答、会话管理等基础链路完全工作后，再扩展股票分析能力（行情工具、计算器、持仓跟踪、行业知识库等）。

> **实现状态（2026-09-30）**：通用 Agent 闭环的前后端骨架均已落地并跑通真实
> 端到端对话（真实 `LITELLM_API_KEY` + `v-flash`，含工具调用）。`server/`
> 包含 `main.py`（FastAPI 路由）、`agent/core.py`（AgentScope Agent 装配）、
> `service/events.py`（AgentScope 事件 → 前端 SSE 契约翻译器）、
> `service/task_manager.py`（工作区/任务注册表 + 每任务 Agent + HITL 确认桥
> 接）、`tools/calculator.py`（受限 AST 四则运算求值器，显式声明 ALLOW 权限
> 避免每次心算都弹确认）。前端已较深度接入 MateChat：`McLayout` 系列（布局
> 骨架 + 自动滚底）、`McBubble`/`McInput`（消息气泡/输入框）、
> `McMarkdownCard`（替换了手写 markdown-it+highlight.js）、`McToolbar`（复
> 制按钮）、`McList`（任务列表）、`McHeader`（顶部栏）、
> `McIntroduction`+`McPrompt`（空状态引导）。详见
> `.github/copilot-instructions.md`「MateChat component usage」一节与
> `TODO.md`「待办」。

---

## 常用开发命令

### 环境准备

必须使用全局指定的 Python 虚拟环境，禁止随意使用系统默认 Python：

```bash
# Python 虚拟环境（用户全局强制约定）
VENV_PYTHON=/media/data/venv/bin/python
VENV_PIP=/media/data/venv/bin/pip

# 确认已装 AgentScope 与 FastAPI
$VENV_PYTHON -c "import agentscope, fastapi, uvicorn; print('AgentScope:', agentscope.__version__, 'FastAPI:', fastapi.__version__)"
```

### 后端开发命令 (FastAPI + AgentScope)

```bash
# 启动后端开发服务（监听 8000 端口，开启热重载）
$VENV_PYTHON -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# 单独测试后端接口连通性（健康检查）
curl -s http://127.0.0.1:8000/api/health

# 单独触发流式对话测试 (SSE)
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，请介绍一下你自己"}'

# 运行后端单元测试
$VENV_PYTHON -m pytest tests/ -v

# 运行单个测试文件或测试用例
$VENV_PYTHON -m pytest tests/test_agent.py -v
$VENV_PYTHON -m pytest tests/test_agent.py::test_chat_endpoint -v
```

### 前端开发命令 (Vue 3 + MateChat)

```bash
cd frontend

# 安装前端依赖（首选 pnpm，次选 npm）
npm install

# 启动前端开发服务器（Vite）
npm run dev

# 生产环境构建与类型检查
npm run build
npm run type-check   # 若已配置 vue-tsc

# 前端代码格式化与 Lint
npm run lint
```

---

## 高层架构与核心设计

```
s_agent/
├── frontend/                          # 前端工程 (Vue 3 + TypeScript + Vite)
│   ├── src/
│   │   ├── main.ts                    # 引入 Vue-DevUI、@matechat/core 与样式
│   │   ├── App.vue                    # 对话主界面 (McLayout, McBubble, McInput)
│   │   ├── api/                       # API 层，封装 SSE EventSource / fetch stream
│   │   └── components/                # 业务组件（后期股票卡片、K 线走势等）
│   └── package.json
├── server/                            # 后端工程 (FastAPI + AgentScope)
│   ├── main.py                        # FastAPI 入口，注册 CORS、路由与异常处理
│   ├── agent/                         # AgentScope 核心定义 (ReActAgent / Agent)
│   │   ├── core.py                    # 通用 Agent 装配逻辑与 Prompt
│   │   └── stock_agent.py             # （后续）股票分析专用 Agent
│   ├── tools/                         # 工具包 (Toolkit)
│   │   ├── calculator.py              # 严禁心算的精密计算工具
│   │   └── tencent_stock.py           # （后续）腾讯公开股票行情接口
│   ├── schemas/                       # Pydantic 数据契约 (请求体、SSE 消息结构)
│   └── config.py                      # 模型配置：从环境变量读取 key，固化 v-flash + litellm base_url
├── portfolio/                         # （后续股票阶段）用户持仓与跟踪 JSON
├── .learnings/                        # 本地持续学习库（严禁纳入 git）
│   ├── knowledge/                     # 捕捉到的技术知识
│   ├── experience/                    # 踩坑与排障经验
│   ├── preference/                    # 用户习惯与阶段偏好
│   └── best_practice/                 # 最佳实践
├── TODO.md                            # 随代码提交的项目待办清单
└── .gitignore                         # 忽略 .learnings/、.claude/、node_modules 等
```

### 后端 AgentScope 版本契约

> ⚠️ **已过时（2026-09-28）**：以下"双版本选型"描述已作废。项目**已升级到 AgentScope 2.0.8**（`pip install -e /media/data/git/agentscope/src/agentscope[service,storage-redis]`，editable 安装），不再使用 1.0.21。保留原文仅供了解演进过程。

~~当前环境 `/media/data/venv` 安装了 `agentscope==1.0.21`，同时本地 `/media/data/git/agentscope/` 存在 2.0 预览源码：~~

~~1. **第一阶段（通用 Agent，推荐）**：使用已安装的 `1.0.21`。~~
~~   - 核心类：`agentscope.agent.ReActAgent`~~
~~   - 流式捕获：`from agentscope.pipeline import stream_printing_messages`~~
~~2. **第二阶段（高阶微服务）**：切至 2.0 并使用 `agentscope.app.create_app()`。~~

**当前实际版本（2026-09-28 生效）**：`agentscope 2.0.8`，editable 模式安装自本地源码。

| 项 | 2.0.8 规范 |
|---|---|
| 核心类 | `from agentscope.agent import Agent`（统一类，非 `ReActAgent`） |
| 流式 API | `agent.reply_stream(msg)` → yield `AgentEvent` |
| 鉴权 | `OpenAICredential(...)` 抽象 |
| 服务层 | `agentscope.app.create_app()`（自动注册 15 个路由） |

⚠️ **升级 1.0.21 → 2.0 时踩中的 4 个 API 破坏性变更**（详见 `.learnings/knowledge/litellm-vflash-integration.md` §4）：
1. `Msg.content` 必须是 **ContentBlock 列表**（`[TextBlock(text=...)]`），不能传字符串。
2. `OpenAIChatModel` 需要 `credential` + `Parameters` BaseModel 实例，传 dict 会报错。
3. `base_url` **只能写在 `OpenAICredential`**，同时写 `client_kwargs.base_url` 会报 "multiple values"。
4. `formatter` 从 `Agent` 移到 `Model`；`stream_printing_messages` 被 `reply_stream()` 取代。

### 前端 MateChat 集成机制

- 核心包：`@matechat/core`、`vue-devui`、`@devui-design/icons`。
- 采用 `fetch` + `ReadableStreamDefaultReader` 或标准 `EventSource` 读取后端 SSE 流，将增量文本逐步追加至当前 Assistant 气泡（`McBubble`）的 `content`，实现打字机效果。

### ⭐ 模型接入：本地 LiteLLM 的 `v-flash`（2026-09-28 端到端验证通过）

本项目**统一使用本机 LiteLLM 代理提供的 `v-flash` 模型**，不直接对接任何厂商原生 SDK。

| 项目 | 值 |
|------|-----|
| 服务端点 | `http://127.0.0.1:4000/v1`（OpenAI 兼容协议） |
| 模型名 | `v-flash`（跨 4 平台 7 节点的虚拟融合模型，自动 fallback 到 Gemini 3.8 Flash） |
| 配置文件 | `/media/data/litellm/config/config.yaml` |
| 认证 | Bearer Token，从环境变量读取，**严禁硬编码** |

**接入写法（AgentScope 2.0.8，2026-09-28 验证通过）**：

```python
from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.formatter import OpenAIChatFormatter
from agentscope.credential import OpenAICredential
from agentscope.tool import Toolkit
from agentscope.message import Msg, TextBlock
from agentscope.event import (
    ReplyEndEvent, TextBlockDeltaEvent, ThinkingBlockDeltaEvent,
)

# 1. Credential（base_url 仅在此处传）
credential = OpenAICredential(
    id="litellm-vflash",
    name="LiteLLM v-flash",
    api_key=os.getenv("LITELLM_API_KEY"),   # SecretStr
    base_url="http://127.0.0.1:4000/v1",
)
# 2. Model（parameters 必须是 BaseModel 实例）
model = OpenAIChatModel(
    credential=credential,
    model="v-flash",
    formatter=OpenAIChatFormatter(),
    parameters=OpenAIChatModel.Parameters(max_tokens=2048),
)
# 3. Agent（formatter 已在 model 上）
agent = Agent(
    name="Assistant",
    system_prompt="你是一个简洁的中文助手。",
    model=model,
    toolkit=Toolkit(),
)
# 4. 调用（content 必须是 ContentBlock 列表）
msg = Msg(name="user", role="user", content=[TextBlock(text="一句话介绍你自己")])
async for event in agent.reply_stream(msg):
    if isinstance(event, TextBlockDeltaEvent):
        yield {"type": "text", "delta": event.delta}
    elif isinstance(event, ThinkingBlockDeltaEvent):
        yield {"type": "thinking", "delta": event.delta}
    elif isinstance(event, ReplyEndEvent):
        yield {"type": "done"}
        break
```

**六个必须遵守的工程陷阱（2026-09-28 实测全部踩中）**：
1. **`max_tokens` 必须 ≥ 2048**：`v-flash` 是推理模型，token 太小时 `content` 返回空。
2. **`base_url` 只能写在 `OpenAICredential`**：同时传给 `client_kwargs` 会报 `multiple values for keyword argument 'base_url'`。
3. **`parameters` 必须是 `OpenAIChatModel.Parameters(...)` BaseModel**：传 dict 会报 `'dict' object has no attribute 'max_tokens'`。
4. **`Msg.content` 必须是 ContentBlock 列表**：传字符串会报 `Input should be a valid list`。
5. **`formatter` 属于 `OpenAIChatModel`，不属于 `Agent`**：写到 `Agent.__init__` 会报 `unexpected keyword argument 'formatter'`。
6. **流式 API 是 `reply_stream()`，不是 `stream_printing_messages`**：后者在 2.0 已删除。

详细调研记录：[.learnings/knowledge/litellm-vflash-integration.md](.learnings/knowledge/litellm-vflash-integration.md)

### ⭐ System Prompt 的实际组装方式（2026-09-30 调研，AgentScope 2.0.8）

发给模型的"系统提示词"**不是** `server/agent/core.py` 里 `SYSTEM_PROMPT_TEMPLATE` 那段字符串本身，而是 AgentScope 在每次 `reply_stream()` 时动态拼出来的三层结构。写新工具、调 System Prompt 措辞、或排查"模型为什么不知道某件事"之前，必须理解这三层：

**第 1 层 —— 项目自己写的固定模板（`server/agent/core.py`）**

```python
SYSTEM_PROMPT_TEMPLATE = (
    "你是 s_agent 工作台里的通用任务助手。你的工作区目录是：\n"
    "{workspace_dir}\n"
    ...
)
```

每个任务第一次发消息时，`build_agent(workspace_dir)` 用该任务的实际工作区绝对路径填充一次 `{workspace_dir}`，传给 `Agent(system_prompt=...)`。**每个任务独立一份，创建时确定，之后不变。**

**第 2 层 —— AgentScope 每轮回复时动态拼接（`Agent._get_system_prompt()`，`agentscope/agent/_agent.py`）**

```python
prompt = [self._system_prompt]                         # 第1层
prompt.append(await toolkit.get_skill_instructions(...))   # 工具包"技能"说明
prompt.append(await offloader.get_instructions())           # 记忆卸载器说明
result = "\n".join(prompt)
# 再经过任意已注册的 system_prompt middleware 依次转换
```

本项目目前**没有**注册任何工具技能（skill）、自定义 offloader 或 system_prompt middleware，所以这两项目前为空、这一层实际等于第 1 层原样。但这是可扩展点：以后给 Toolkit 挂技能说明、或换成自定义记忆卸载策略，会自动拼进去，不需要改 `SYSTEM_PROMPT_TEMPLATE` 本身。

**第 3 层 —— 运行时状态提醒，注意：不进 system prompt 字符串，是独立的上下文消息**

`InjectionConfig.inject_runtime_state` 默认 `True`（本项目未覆盖，走默认值），AgentScope 在每轮回复开始时会往**对话上下文**（`self.state.context`，不是 system prompt）追加一条 `<system-reminder>` 消息，内容包含：
- 当前时间（`InjectionConfig.timezone` 默认 `UTC`，本项目未改成 `Asia/Shanghai`）
- 待办任务列表（若用了 `TaskCreate`/`TaskList` 建过任务）
- 上下文长度接近压缩阈值时的提醒

官方注释原话："We attach a `HintBlock` instead of mutating the system prompt, so that prompt caching still works" —— 故意不塞进 system prompt 字符串，是为了让 system prompt 本体保持不变，方便模型服务商做 prompt caching。

⚠️ **已知缺口**：这个 `HintBlockEvent` 目前 `server/service/events.py` 的 `AgentEventTranslator.translate()` 没有对应分支，会落入默认 `return []` 被静默丢弃——即它确实影响了模型看到的内容，但不会转成任何 SSE 帧显示给前端用户。

**最终发给模型 API 的实际结构**：

```python
messages = [
    SystemMsg(第1+2层拼好的字符串),
    UserMsg(压缩摘要，仅发生过上下文压缩后才有),
    *self.state.context,   # 历史对话 + 第3层插入的 <system-reminder> 消息
]
tools = await toolkit.get_tool_schemas(...)  # 12 个工具的 JSON Schema，走 OpenAI API 的独立 tools 字段，不占用文本
```

也就是说模型实际看到的完整指令 = 固定系统提示词（项目写的）+ 动态运行时提醒（框架自动插入，独立消息）+ 工具函数签名（走 API 结构化字段，完全不占文本篇幅）。

### ⭐ 会话历史持久化（2026-09-30，AgentScope 2.0.8）

`server/service/memory_store.py` 用本地 Redis 容器（端口 6380）持久化每个任务的对话历史，跨后端进程重启存活（已用 `kill -9` 验证）。核心机制：

- 持久化单元是 `agentscope.state.AgentState`——一个纯 pydantic `BaseModel`，包含 `context`（完整消息历史）、`summary`（压缩摘要）等全部子上下文。`agent.state.model_dump_json()` / `AgentState.model_validate_json(...)` 可以直接序列化/反序列化，`Agent(state=...)` 构造参数直接接受恢复后的对象——**不需要自己拼消息列表**，这是 AgentScope 官方 Redis/SQL 存储后端（`agentscope.app.storage`）内部用的同一套机制。
- 只在 `ReplyEndEvent`（整轮真正结束）时保存，不在工具调用等待 HITL 确认期间保存——否则恢复出来的状态会包含"工具调用发出了但没有结果"，`reply_stream()` 对着这种状态会直接抛错（`"Agent is waiting for N tool calls ... but received no event"`）。
- 保存失败要"尽力而为"（记日志不抛出）——因为保存发生在该轮的 SSE 帧（含 `done`）已经发给前端**之后**，抛出去只会导致外层 except 再补发一个多余的 `done`/错误帧。加载失败则相反，直接往外抛，交给已有的"缺 API key"式优雅降级处理——历史读取失败应该让用户看到明确报错，而不是默默当成"没有历史"。

⚠️ **官方在线文档 `doc.agentscope.io` 的 State/Session Management 页面与本地实际安装的 2.0.8 源码完全对不上**：文档描述的是 `StateModule` / `agent.state_dict()` / `agent.load_state_dict()` / `agentscope.session.JSONSession` 这套 API，但本地安装（`/media/data/git/agentscope/src/agentscope`，editable 模式）里 `agentscope.session` 模块根本不存在（`import` 直接报 `ModuleNotFoundError`），`Agent` 也没有 `state_dict()` 方法。遇到类似情况——**以本地实际安装的源码为准，别信在线文档**，这也是本项目从 1.0.21 升级到 2.0 时已经踩过的同一类坑（见上文"后端 AgentScope 版本契约"）。

> 完整设计（含任务间隔离性的实测验证、Redis 自身持久化可靠性的实测边界、
> 与原规划文档的差异对照）见
> [docs/specs/2026-09-30-conversation-memory-management.md](docs/specs/2026-09-30-conversation-memory-management.md)。

### ⭐ AgentScope 内部待办（Todo）透传（2026-09-30 全链路打通）

AgentScope 2.0 的 `TaskCreate` / `TaskUpdate` / `TaskGet` / `TaskList` 4 个内置工具允许模型自主拆解复杂多步任务。其数据源位于 `AgentState.tasks_context.tasks`（纯 Pydantic 对象，自动随 AgentState 存入 Redis）。项目现已打通从框架内部到前端 UI 的全链路透传：

- **数据契约与规范**：详见 [docs/specs/2026-09-28-todo-display.md](docs/specs/2026-09-28-todo-display.md)。
- **后端序列化**：`server/service/history.py::serialize_todos` 将 AgentScope `Task`（含 `blocks` / `blocked_by` 依赖关系、软删除 `deleted` 处理）清洗转为前端 `TodoItem` 格式。
- **双通道更新**：
  1. **冷启动**：前端切任务或刷新时通过 `GET /api/tasks/{task_id}/todos` 全量同步。
  2. **热更新（SSE）**：后端在 `TaskCreate`/`TaskUpdate` 成功执行以及每轮对话结束（`ReplyEndEvent`）时，主动 yield 一帧 `task_todos_changed` 事件，前端整体替换快照。
- **前端呈现**：右侧结果区第 5 个 Tab（`待办`）通过 `TodoPanel.vue` 展示带依赖提示、状态图标、折叠删除过滤的 todo 列表；状态变化驱动 `todos` Pinia store。

---

## 核心行为准则（继承全局与本地最佳实践）

未来 Claude Code 实例在此仓库工作时，**必须严格遵守**以下规则：

### 1. 知识沉淀与内容递增（强制性）
- 必须严格遵循**内容递增原则**：严禁删除或精简既有的有效内容，除非信息确已过时或存在冲突。
- 新信息以追加或合并方式写入 `.learnings/`，并在原过时内容末尾标注 `> ⚠️ 已过时：[原因]`。
- 任何新增或修改，必须实时双向同步 `.learnings/index.md`。
- **高频问题（出现 2 次及以上）**必须提炼并提升至本 `CLAUDE.md` 中。

### 2. Git 提交隔离（强制性）
- `.learnings/` 与 `.claude/` 目录属于本地私有与知识库，**严禁**纳入版本控制。已在 `.gitignore` 声明，提交前务必确认 `git status` 无这两个目录。
- `TODO.md` 必须纳入版本控制，与业务代码一同提交。

### 3. TODO.md 维护与任务推荐（强制性）
- 每次会话开始时，先查看 `TODO.md` 获取上下文。
- 任务完成后将条目移至“已完成”并注明日期，**严禁直接删除**。
- 每次回答或交付完成后，必须根据 `TODO.md` 主动向用户推荐 1~3 条具体的下一步行动。

### 4. 后续股票分析阶段特殊准则（提前固化）
进入股票分析功能改造后，必须继承本地成熟经验：
- **⭐ 严禁心算**：任何算术运算（浮盈、收益率、百分比、Sharpe、回撤、复利等超过两个数字的运算），必须调用 Python 代码/计算器工具，**禁止 LLM 自算**。
- **⭐ JSON 写入规范**：写入 `portfolio/*.json` 时，**严禁在 string value 中使用任何形式的引号**（英文 `"`、中文 `“`/`”`、单引号 `'`）。强调请用全角【】或顿号；写入后必须用 `json.load()` 自检。
- **⭐ A 股节前效应必检**：分析日期距长假（国庆、春节等）≤ 7 个交易日时，必须主动提示节前效应可能引发缩量避险，不可将季节性缩量回调误判为基本面恶化。
- **⭐ argparse 避免特殊符号**：编写 CLI 工具时，避免在 help 文本中使用 `%`、`→`，统一用 ASCII 字符以防解析异常。
- **⭐ 合规边界**：不给用户做“必须买/必须卖”的绝对承诺，只提示风险与机会，决策权在用户。

---

## 相关引用与学习路径

- 架构桥接方案：[.learnings/knowledge/agentscope-matechat-architecture.md](.learnings/knowledge/agentscope-matechat-architecture.md)
- 阶段演进偏好：[.learnings/preference/project-evolution.md](.learnings/preference/project-evolution.md)
- 项目任务追踪：[TODO.md](TODO.md)
- 知识库索引：[.learnings/index.md](.learnings/index.md)
- 会话与记忆管理设计：[docs/specs/2026-09-30-conversation-memory-management.md](docs/specs/2026-09-30-conversation-memory-management.md)
- 本地 AgentScope 源码参考：`/media/data/git/agentscope/`
- 本地股票分析与行情接口参考：`/media/data/git/股票分析/`
