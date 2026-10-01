# Multi-Agent 动态子智能体运行时 (Dynamic Sub-Agent Runtime) 与 LLM Wiki 知识沉淀架构设计规范

> **规范版本**：v2.3  
> **创建日期**：2026-10-01  
> **更新日期**：2026-10-01（根据架构审查全面补全：隔离机制与凭证传递、HITL 防越权沙箱、分级超时与轮数策略、Wiki 防二次膨胀汇报契约、命名风格一致化）  
> **目标分支**：`feat/multi-agent`  
> **状态**：方案设计中（待确认后实施编码）  
> **责任范围**：`server/agent/subagents/`、`server/agent/tools_subagent.py`、`server/agent/tools_wiki.py`、`server/service/wiki_store.py`、`server/agent/core.py`、`tests/test_subagents.py`

---

## 1. 背景与核心诉求

### 1.1 现状痛点
在 `s_agent` 跑通基础三栏工作台并具备腾讯股票量化、SQLite 结构化数据存储与 Tavily 全网搜索后，当前采用的单体 ReAct Agent（`server/agent/core.py`）在面对复杂的深度投资研报任务时面临明显瓶颈：
1. **上下文爆炸与注意力稀释（Context Bloat & Attention Dilution）**：
   - 进行一次深度投研往往需要遍历全网 5~15 篇新闻研报与数十个财报指标。海量未经清洗的原始文本（HTML、搜索引擎摘要、长篇研报）直接充斥主会话，迅速消耗 Context Window（Token 暴涨），并导致模型在多轮对话后遗忘早期核心约束。
2. **多重角色认知混淆与主 Agent 工具严重臃肿（Role Confusion & Tool Bloat）**：
   - 主 Agent 挂载了近 **30 个底层工具**（爬虫、分时盘口、复权K线、SQLite 建表与写入、Python 终端、计算器等）。光是加载工具 Schema 就要消耗数千 Token。主 Agent 既要负责宏观规划，又忍不住自己去调接口写代码，经常陷入细节泥潭，导致工具误调用（Tool Hallucination）与幻觉。
3. **“知识不累积、每次从零开始”（RAG 的固有弊端）**：
   - 传统 RAG 仅依赖临时的向量片段切片，查询结束后知识随会话销毁。当用户上一次调研了“伊利股份生鲜乳周期”，下一次询问“蒙牛与伊利成本对比”时，Agent 无法站在前一次研究的肩膀上，依然消耗大量 Token 重新去外网盲搜。
4. **硬编码静态子智能体的局限性（Hardcoded Sub-Agents Limitation）**：
   - 若在代码中写死固定几个子智能体类，无法应对真实世界千变万化的垂直需求（如：白酒批价调研、光伏逆变器海关出口跟踪、破产重整法律审查等）。必须赋予系统动态按需生成任意专家的能力。

### 1.2 架构目标
- **主协调 Agent 大幅瘦身（Lean Orchestrator Agent）**：
  - 主 Agent 从近 30 个工具大幅裁减至 **11~12 个管理与元认知工具**；
  - 核心职责纯粹聚焦于：**意图理解、待办拆解、动态委派、大局掌控、研报合成、交付落盘**；
  - **绝不亲自**去爬网页、跑 Python 脚本、写复杂 SQL。
- **专业工具全面下沉至「底层工具资源池（Tool Pool）」**：
  - Tavily 全网搜索、腾讯行情与盘口、SQLite 数据读写、受限 Python/Bash、高精度计算器等专业工具全部下沉；
  - 由主 Agent 在调用 `delegate_task` 时，通过**白名单权限沙箱（Tool Sandboxing）**按需授权给特定的子智能体。
- **动态子智能体运行时（Dynamic Sub-Agent Runtime / JIT Sub-Agent）**：
  - 主 Agent 通过统一委派工具 `delegate_task(role, instruction, allowed_tools, base_template)` 动态召唤任意领域专家；
  - 子智能体在纯净、隔离的短命上下文容器中执行，完成后向主 Agent 提交结构化报告并销毁子上下文，主会话零污染。
- **全量落维基，高密摘要回传（Anti-Context Bloat Reporting）**：
  - 彻底杜绝子 Agent 将 1~2 万字爬虫原文抛回给主 Agent 引发主 Context 二次爆炸；
  - 子 Agent 将详尽底稿落盘维基（`data/wiki/`），仅回传 300~600 字的高浓度结构化摘要与文件路径，主 Agent 按需查阅。
- **自适应任务主题命名交付**：
  - 严禁机械套用模板名，主 Agent 严格根据用户具体提问自适应生成见名知义的交付研报（如 `乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`）并落盘工作区供右侧面板预览。

---

## 2. 总体架构：极简总指挥与下沉工具池

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MateChat 前端工作台                             │
│       左栏: 任务与工作区  |  中栏: 对话流与待办  |  右栏: 产物与预览     │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ SSE 流式事件 (ToolCall / ToolResult)
┌───────────────────────────────────▼────────────────────────────────────┐
│              主协调智能体 (Lean Orchestrator Agent - 仅 11 个工具)        │
│                                                                        │
│  【核心委派】 delegate_task (最核心，元调度)                             │
│  【待办管理】 TaskCreate, TaskUpdate, TaskList, TaskGet (前端待办联动) │
│  【交付落盘】 Write, Read, Edit, Glob (研报合成与工作区落盘)            │
│  【人机澄清】 AskUser (模糊需求向用户提问)                               │
│  【维基导航】 wiki_query, wiki_read (高层目录检索与历史成果查阅)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ delegate_task(role, instruction, allowed_tools)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             动态子智能体运行时 (Dynamic Sub-Agent Runtime)               │
│                                                                        │
│   ┌───────────────────────────┐      ┌───────────────────────────┐     │
│   │   动态子智能体 A (调研专家)  │      │   动态子智能体 B (建模精算) │     │
│   ├───────────────────────────┤      ├───────────────────────────┤     │
│   │ 注入: Research底座 + 指令 │      │ 注入: Finance底座 + 指令  │     │
│   │ 沙箱工具: web_search,     │      │ 沙箱工具: python_calc,    │     │
│   │          wiki_tools       │      │          finance_db       │     │
│   │ 独立上下文: 阅后即焚      │      │ 独立上下文: 阅后即焚      │     │
│   │ 沉淀: 全量入 data/wiki/   │      │ 沉淀: 指标入DB/底稿入Wiki │     │
│   │ 汇报: 300~600字高密摘要   │      │ 汇报: 300~600字精算摘要   │     │
│   └─────────────┬─────────────┘      └─────────────┬─────────────┘     │
└─────────────────┼──────────────────────────────────┼───────────────────┘
                  │                                  │
                  │   从下沉资源池中按需绑定工具沙箱   │
                  ▼                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  下沉的底层工具资源池 (Specialized Tool Pool)           │
│                                                                        │
│  • web_search:    mcp__tavily__tavily-search, tavily-extract           │
│  • stock_market:  stock_quote, stock_kline, stock_minute, stock_handicap│
│  • python_calc:   受限 Bash/Python 环境, calculate 精准计算器          │
│  • finance_db:    SQLite 事实表读写, finance_record_metric, sql 查询    │
│  • wiki_mutate:   wiki_save_page (定性分析底稿与实体页面编译沉淀)       │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 跨任务持久化与复用
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     双轨制持久化层 (Persistence Layer)                  │
│                                                                        │
│  【轨道 A: 定量关系型数据库】               【轨道 B: 定性认知 LLM Wiki】 │
│   SQLite (data/finance_db.sqlite)        Markdown 维基 (data/wiki/)    │
│   • 标的元数据 (stocks)                   • 规则规范 (SCHEMA.md)        │
│   • 日度估值行情 (stock_daily_quotes)     • 目录索引 (index.md)         │
│   • 增量 K 线 (stock_kline_records)       • 变更日志 (log.md)           │
│   • 财务指标事实 (financial_metrics)      • 标的档案 (entities/)        │
│   • 核心自选池 (user_watchlist)           • 宏观行业 (industries/)      │
│                                          • 专题底稿 (analyses/)        │
│                                          • 原始证据 (raw/)             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 动态子智能体运行时架构深水区设计

### 3.1 统一工具契约（Tool Schema）

```python
def delegate_task(
    role: str,
    instruction: str,
    allowed_tools: list[str],
    base_template: str = "general",
    timeout_seconds: int = 0,
    max_iters: int = 0,
    persist_to_wiki: bool = True,
) -> str:
    """
    动态生成并委派一个具有专属角色和限定工具集的子智能体（Sub-Agent）去执行专业子任务。
    子智能体拥有完全隔离的上下文，执行完毕后向主智能体汇报结构化成果。

    参数:
        role: 子智能体的专业角色定义（如："资深乳品行业调研员"、"CPA财务精算与估值建模师"、"红队风险审查员"）
        instruction: 主 Agent 下达的具体任务目标、分析范围与交付要求
        allowed_tools: 授权该子智能体使用的工具组别名（web_search, stock_market, python_calc, finance_db, wiki_tools）或单个工具名
        base_template: 基础底座模板类型，可选值:
                       - "research": 适合搜索、研报解读与定性分析（默认超时 300s, max_iters=15）
                       - "finance": 适合数据建模、报表核算与公式计算（默认超时 180s, max_iters=10）
                       - "reviewer": 批判性审查与逻辑挑刺（默认超时 120s, max_iters=8）
                       - "general": 通用分析与代码任务（默认超时 60s, max_iters=8）
        timeout_seconds: 自定义超时秒数（0 表示使用模板默认值）
        max_iters: 自定义最大推理迭代轮数（0 表示使用模板默认值）
        persist_to_wiki: 是否授权子智能体将高价值认知与测算底稿自动写入本地投研维基 data/wiki/（默认为 True）
    返回:
        子智能体完成任务后的高浓度结构化摘要与事实底稿路径（300~600字以内）。
    """
```

---

### 3.2 运行时生命周期与隔离实现细节（针对 Review 核心问题解答）

#### 1. 模型与凭证传递机制（Credential & Model Sharing）
- **复用而非重复构造**：Sub-Agent 不新建不同的账户凭据，而是复用主 Agent 构建环境中的 `OpenAICredential(id="litellm-credential", name=effective_model, api_key=config.LITELLM_API_KEY, base_url=effective_base_url)`；
- **独立 Model 实例**：为每个子智能体实例化一个全新的 `OpenAIChatModel`，使用相同的 `credential`、`OpenAIChatFormatter` 与相同的 `context_size`；
- **`max_tokens` 强保障（规避 CLAUDE.md 第 6 陷阱）**：模型构造参数中显式设置 `parameters=OpenAIChatModel.Parameters(max_tokens=config.MODEL_MAX_TOKENS)`（例如 4096~8192），**彻底杜绝推理模型因 `max_tokens` 过小而返回空 content 的已知缺陷**。

#### 2. 工作区与环境隔离（Workspace & CWD Isolation）
- **共享物理产物，隔离会话状态**：
  - 子 Agent 接收 `workspace_dir: Path`（与主会话同一目录），绑定独立的 `LocalWorkspace(workdir=str(workspace_dir))`；
  - 子 Agent 的执行环境 block 注入该工作区绝对路径及 `data/wiki/` 绝对路径；
  - 子 Agent 具有完全隔离的 `AgentState` 实例与独立的上下文消息数组（`state.context`），其多轮 ReAct 的中间试错消息阅后即焚，不持久化到 Redis 主会话键中。

#### 3. HITL 权限控制与工作空间内完全授权（Permission Inheritance & Workspace Full Authorization）
- **工作空间内完全授权原则（Full Authorization for Workspace Operations）**：
  - 核心共识：凡是在任务工作空间（`workspace_dir`）和本地维基知识库（`data/wiki/`）范围内的常规操作，以及主 Agent 派发给子智能体沙箱的垂直业务工具，必须给予**完全授权（ALLOW）**，实现自主闭环推进，绝不因缺少人工交互弹窗而中断执行流；
  - 杜绝子智能体等待授权假死：子智能体运行于无人工确认通道的独立异步沙箱中（调用 `agent.reply()`），由于外部 MCP 工具（如 Tavily 检索）与部分非只读工具在 AgentScope 默认策略下会被标记为 `ASK`，必须在子智能体引擎初始化时，对主 Agent 授予该子智能体的所有业务工具统一注入 `PermissionBehavior.ALLOW` 白名单规则，确保子智能体完全自主执行；
- **沙箱安全与防权限外溢（Sandbox Safety & Anti-Escalation）**：
  - 子智能体采用与主 Agent 一致的 `PermissionMode.ACCEPT_EDITS` 安全模式，不使用全量无规则绕过；
  - **白名单路径约束**：文件读写工具（`Write`、`Edit`）仅允许操作 `{workspace_dir}/**` 与 `data/wiki/**`；若尝试向系统根目录、敏感配置文件等外部路径写文件，依然会被底层拦截；
  - **`Bash` 权限收紧**：子智能体中的 `Bash` 工具**仅限运行 Python 脚本和数据计算**（`python:*`、`python3:*` 等），严禁执行提权命令或系统破坏性命令（如 `rm -rf /` 等，底层自动拦截为 `ASK` 阻止执行）；
  - **越权防御**：若子智能体企图执行白名单之外或超出工作区的操作，AgentScope 引擎直接触发权限拦截并抛出错误信息给子智能体模型，由其自主调整策略。

---

### 3.3 动态超时与推理步数分级规范（Tiered Timeouts & Adaptive Max Iters）

为解决原先 120s / 8 步一刀切导致研报抓取超时、推理模型过早截断的问题，系统采用**分级配置矩阵**：

| 模板类型 (`base_template`) | 默认超时 (`timeout_seconds`) | 默认迭代步数 (`max_iters`) | 依据与设计考量 |
| :--- | :--- | :--- | :--- |
| **`research`** (深度行业调研) | **300 秒 (5分钟)** | **15 步** | 涵盖多轮 Tavily 搜索、5~15 篇网页提取（每篇 10~25s）、交叉比对与维基写入，需充足时间与步数。 |
| **`finance`** (财务报表建模) | **180 秒 (3分钟)** | **10 步** | 涵盖 2~4 次 Python 脚本编写与调试、SQLite 数据提取、DCF 敏感性测算与持久化落库。 |
| **`reviewer`** (红队风险排查) | **120 秒 (2分钟)** | **8 步** | 侧重对已收集材料的逆向审阅与逻辑挑刺，少有外部网络开销。 |
| **`general`** (通用短任务) | **60 秒 (1分钟)** | **8 步** | 简单计算、文件格式转换或特定字段查询，追求极速响应。 |

> 主 Agent 在调用 `delegate_task` 时，亦可通过显式传参 `timeout_seconds=400, max_iters=20` 覆盖默认值。

---

### 3.4 汇报契约与防二次膨胀机制（Anti-Context Bloat Reporting Contract）

**核心治理原则：全量落维基，高密摘要回主脑（Offload to Wiki, Return Compact Summary）**。

若子 Agent 爬取了 10 篇研报或生成了 1~2 万字测算底稿，**严禁**直接将全文作为 ToolResult 返回给主 Agent，否则主 Agent 的 Context Window 将立即面临二次爆炸。

#### 1. 子智能体汇报标准规范（300~600 字以内）
子智能体必须遵循统一的 4 段式汇报格式：

```markdown
### 【<子任务角色名>·交付摘要】<标的或主题>
- **核心结论**：[3~5句话阐明最核心的定论与事实推演]
- **关键数据指标**：[包含核心测算数值的微型表格或关键比率]
- **维基沉淀路径**：[指明详尽底稿已写入哪个维基文件，如 `data/wiki/entities/sh600887.md` 或 `data/wiki/analyses/2024-h1-yili-fcf.md`]
- **信源与存疑提示**：[关键信源出处、未解决的分歧或需主 Agent 留意的风险]
```

#### 2. 主 Agent 按需解压机制
- 主 Agent 基于该 300~600 字的高浓度报告起草最终研报；
- 若主 Agent 需进一步获取特定章节细节，可使用已有的 `wiki_read` 或 `Read` 工具**精准按需读取**对应片段，绝不一股脑塞入上下文。

---

### 3.5 Schema 与工具命名风格一致化规范（Naming Conventions & Schema Consistency）

统一遵循标准的 Python 社区与 REST 风格：**所有工具名、别名、入参出参一律使用 `snake_case`**。

#### 1. 工具组别名（Presets）与下沉工具映射矩阵

```python
TOOL_GROUP_REGISTRY: dict[str, list[str]] = {
    "web_search": [
        "mcp__tavily__tavily-search",
        "mcp__tavily__tavily-extract",
    ],
    "stock_market": [
        "stock_quote",
        "stock_batch_quotes",
        "stock_kline",
        "stock_minute",
        "stock_handicap",
        "market_index_overview",
    ],
    "python_calc": [
        "Bash",          # 严格绑定 Python 白名单沙箱
        "calculate",     # 高精度数学表达式
    ],
    "finance_db": [
        "finance_overview",
        "finance_watchlist",
        "finance_record_metric",
        "sqlite_query",
        "sqlite_execute",
    ],
    "wiki_tools": [
        "wiki_query",
        "wiki_read",
        "wiki_save_page",
    ],
    "file_io": [
        "Read",
        "Write",
        "Edit",
        "Glob",
    ],
}
```

#### 2. 统一错误返回协议（Standardized Error Payload）
当子智能体出现超时、执行异常或权限越界时，运行时向主 Agent 返回标准格式错误：
```json
{
  "status": "error",
  "error_type": "TimeoutError | PermissionError | ExecutionError",
  "partial_result": "子智能体在异常前已获取的阶段性结论...",
  "suggestion": "主 Agent 可以尝试缩小搜索范围或调整指令重新委派"
}
```

---

## 4. 主协调智能体的极简工具矩阵（Lean Orchestrator Toolset）

主 Agent 的角色定义纯粹为**“首席分析师 & 任务调度编排总监”**，仅保留 11~12 个管理工具：

| 职责分类 | 保留工具名称 | 职责定位 |
| :--- | :--- | :--- |
| **调度核心** | **`delegate_task`** | 动态委派子智能体（指派角色、指令、工具沙箱白名单） |
| **待办编排** | `TaskCreate`<br>`TaskUpdate`<br>`TaskList`<br>`TaskGet` | 负责将投研大任务拆解为推进步骤，与前端中栏待办卡片实时同步联动 |
| **交付落盘** | `Write`<br>`Read`<br>`Edit`<br>`Glob` | 汇总各子任务底稿，起草自适应命名的最终研报，落盘至 `{workspace_dir}/` |
| **人机交互** | `AskUser` | 遇到关键需求歧义时向用户提问澄清 |
| **维基全局导航**| `wiki_query`<br>`wiki_read` | 规划前轻量检索维基总索引（`index.md`），查阅是否已有历史沉淀 |

> 主 Agent 绝不直接挂载 `mcp__tavily__*`、`stock_*`、`Bash` 或 `sqlite_*`，彻底杜绝越俎代庖与注意力稀释。

---

## 5. LLM Wiki 投研知识沉淀体系设计

本体系深度融合 Andrej Karpathy 的经典设计与学术界“持续知识编译（Continual Knowledge Compilation）”范式。

### 5.1 三层知识结构

1. **不可变证据层（Raw Sources: `data/wiki/raw/`）**：
   - 存放下载的研报 PDF 文本抽取件、公司财报原件、Tavily 网页清洗前的完整快照；
   - **特性**：只读不可变（Immutable），作为系统追溯审计的绝对事实源（Ground Truth）。
2. **编译维基层（The Wiki: `data/wiki/`）**：
   - 由 Sub-Agent 与主 Agent 共同编写与维护的结构化 Markdown 页面；
   - 页面内部支持显式 Markdown 双向超链接（如 `[生鲜乳周期](../industries/raw-milk-cycle.md)`）；
   - **子目录划分**：
     - `entities/`：个股与公司标的百科（如 `sh600887.md`、`hk02319.md`），沉淀主营业务拆解、竞争壁垒、核心护城河、历次评级演变；
     - `industries/`：行业赛道与宏观周期（如 `dairy-industry.md`、`raw-milk-cycle.md`），沉淀供需拐点、上游成本传导机制、政策监管风向；
     - `analyses/`：深度专题研究与估值测算底稿（如 `2024-h1-yili-cashflow-deepdive.md`），沉淀商业逻辑推理与自由现金流测算过程。
3. **治理与规则层（The Schema: `data/wiki/SCHEMA.md`）**：
   - 维基维护公约，指导 Agent 遵守统一的排版规范、命名约定、冲突消解原则（新观点如何与旧结论融合）与自检流程。

### 5.2 导航与审计双核心文件

- **`data/wiki/index.md`（内容索引总览）**：
  - 维基的地图。按分类编排所有已沉淀的页面链接、一句话核心概述、涉及标的代码与最后更新时间；
  - **检索加速**：Agent 在执行查询时，**首先读取 `index.md`**，快速锁定相关页面，避免在大量文件中盲目搜索，省去复杂的向量切片基础设施。
- **`data/wiki/log.md`（时间戳审计日志）**：
  - 纯追加（Append-only）的流水账，记录谁在何时做了什么更新；
  - 统一采用易解析的前缀格式：
    ```markdown
    ## [2026-10-01 16:30] research_analyst | ingest | 新增生鲜乳行业周期分析 (industries/raw-milk-cycle.md)
    ## [2026-10-01 16:32] financial_modeler | update | 更新伊利股份2024H1现金流测算 (entities/sh600887.md)
    ```

---

## 6. 详细模块与类设计

```
server/
├── agent/
│   ├── core.py                   # 主 Agent 构建工厂（仅挂载 11 个管理工具，精简 Prompt）
│   ├── subagents/                # 动态子智能体套件目录
│   │   ├── __init__.py           # 导出公共类
│   │   ├── runner.py             # DynamicSubAgentRunner: 隔离上下文容器与短命执行器
│   │   ├── templates.py          # 预设基础模板库 (research, finance, reviewer, general)
│   │   └── tool_resolver.py      # 工具白名单解析器 (将 Preset 展开为具体下沉工具实例)
│   ├── tools_subagent.py         # 将 delegate_task 封装为 FunctionTool
│   └── tools_wiki.py             # 暴露给 Agent 的 Wiki 原生工具 (wiki_query, wiki_read, wiki_save_page)
└── service/
    ├── finance_db.py             # 已有的 SQLite 结构化数据服务
    └── wiki_store.py             # LLM Wiki 底层存储管理器（原子读写、索引维护、日志追加）
```

---

## 7. 主 Agent 协同调度与自适应命名交付

### 7.1 多智能体标准协同 SOP

主 Agent 在收到用户深度投研指令后，严格执行以下 4 步工序：

1. **第 1 步：大纲规划与维基查阅**  
   - 先调用 `wiki_query` 查阅是否已有关于该标的或行业的研究底稿；
   - 调用 `TaskCreate` 创建多步待办（如：1. 行业周期与公司动态调研 2. 核心财务指标穿透建模 3. 综合报告合成 4. 交付落盘）；
2. **第 2 步：按需动态委派（按需召唤专家）**  
   - 针对调研任务：调用 `delegate_task(role="...", instruction="...", allowed_tools=["web_search", "wiki_tools"], base_template="research")`；
   - 针对测算任务：调用 `delegate_task(role="...", instruction="...", allowed_tools=["python_calc", "finance_db", "wiki_tools"], base_template="finance")`；
   - 针对风险审查：调用 `delegate_task(role="...", instruction="...", allowed_tools=["Read", "wiki_tools"], base_template="reviewer")`；
3. **第 3 步：自适应主题命名与交付落盘（Dynamic Artifact Generation）**  
   - 主 Agent 汇总各子智能体返回的高质量事实底稿与测算数据，起草结构化报告；
   - **严格按照用户具体诉求自适应命名交付文件**，使用 `Write` 工具落盘到 `{workspace_dir}/`：
     - **单标的综合研报**：`{workspace_dir}/<标的名称>_深度投资分析.md`（如 `伊利股份_深度投资分析.md`）；
     - **同业横向对比**：`{workspace_dir}/<行业名称>_<对比标的>_横向对比与竞争格局.md`（如 `乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`）；
     - **行业/宏观专题**：`{workspace_dir}/<行业或赛道>_<研究主题>.md`（如 `生鲜乳行业_供需周期与成本拐点展望.md`）；
     - **专项财务/估值测算**：`{workspace_dir}/<标的名称>_<报告期或主题>_专项财务测算.md`（如 `伊利股份_2024H1_自由现金流与回购增厚测算.md`）；
     - **风险审查与红队挑战**：`{workspace_dir}/<标的名称>_<关注点>_红队风险排查报告.md`；
   - 文件写入后，前端右侧「产物/预览」面板实时可见，支持在线阅读、大纲导航、新标签页沉浸预览与一键下载；
4. **第 4 步：状态同步**  
   调用 `TaskUpdate` 标记所有步骤完成。

---

## 8. 测试策略与验收标准

### 8.1 单元测试（`tests/test_subagents.py` & `tests/test_wiki_store.py`）
- **Lean Toolset 测试**：
  - 验证主 Agent 挂载的工具集严格限制在管理类工具，不包含任何爬虫与行情工具；
- **ToolResolver 单元测试**：
  - 测试工具组别名（`web_search`, `python_calc` 等）正确展开为底层下沉工具列表；
  - 测试防递归机制（Sub-Agent 无法解析获取 `delegate_task` 工具）；
- **DynamicSubAgentRunner 独立执行测试**：
  - 测试动态注入 Prompt 与工具沙箱执行；
  - 测试分级超时（research 300s, general 60s）与异常兜底，确保主 Agent 永不挂死；
- **WikiStore 单元测试**：
  - 维基目录自动初始化、`SCHEMA.md`、`index.md` 与 `log.md` 骨架验证；
  - `save_page` 写入同时自动更新 `index.md` 索引与追加 `log.md` 日志。

### 8.2 端到端投研实战验收
- **实测场景**：
  - 用户提问：“对比伊利与蒙牛的自由现金流、上游原奶周期影响及海外布局，生成对比研报”；
  - 验收指标：
    1. 主 Agent 仅调用 `delegate_task` 派发子任务，自身无任何爬虫与 Python 运算调用；
    2. 主会话 Token 消耗相比单 Agent 减少 **60%~70%**；
    3. 工作区生成规范自适应命名的交付文件：`乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`；
    4. 事实与测算分别沉淀至 `data/wiki/` 与 SQLite。

---

## 9. 实施任务分解（待确认后执行）

- [ ] **Task 1**：实现 `server/service/wiki_store.py`（LLM Wiki 底层存储管理器、索引自动维护与日志审计流）；
- [ ] **Task 2**：实现 `server/agent/tools_wiki.py`（封装 `wiki_query`, `wiki_read`, `wiki_save_page` 等原生工具）；
- [ ] **Task 3**：实现 `server/agent/subagents/templates.py`（预设 base templates 及分级超时/步数：research, finance, reviewer, general）；
- [ ] **Task 4**：实现 `server/agent/subagents/tool_resolver.py`（构建下沉工具池与沙箱白名单解析器，剥离 `delegate_task`，执行权限沙箱校验）；
- [ ] **Task 5**：实现 `server/agent/subagents/runner.py`（DynamicSubAgentRunner 动态生命周期执行容器，集成凭证共享、独立模型、防二次膨胀汇报截断与超时控制）；
- [ ] **Task 6**：实现 `server/agent/tools_subagent.py`（封装 `delegate_task` 为主 Agent 可调用的 FunctionTool）；
- [ ] **Task 7**：重构 `server/agent/core.py`（剥离下沉专业工具，仅为主 Agent 挂载 11 个极简管理工具，彻底精简主 Prompt 与 Token 消耗）；
- [ ] **Task 8**：编写单元测试（`tests/test_wiki_store.py`, `tests/test_subagents.py`）并完成全量回归与实战验证。
