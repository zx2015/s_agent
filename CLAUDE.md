# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位与演进路线

本项目是一个**前后端分离的通用智能体（Agent）平台**，前期跑通基础对话闭环，后期改造演进为**股票分析智能体**：
- **前端**：基于华为 DevUI 团队开源的 **MateChat**（Vue 3 + TypeScript + Vite）。
- **后端**：基于 **AgentScope** 框架构建智能体核心，使用 **FastAPI** 对外暴露 SSE（Server-Sent Events）流式接口。
- **演进原则**：**先通用后专用**。必须在通用 Agent 的 SSE 流式一问一答、会话管理等基础链路完全工作后，再扩展股票分析能力（行情工具、计算器、持仓跟踪、行业知识库等）。

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
- 本地 AgentScope 源码参考：`/media/data/git/agentscope/`
- 本地股票分析与行情接口参考：`/media/data/git/股票分析/`
