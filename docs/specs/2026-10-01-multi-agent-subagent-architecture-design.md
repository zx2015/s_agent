# Multi-Agent 动态子智能体运行时 (Dynamic Sub-Agent Runtime) 与 LLM Wiki 知识沉淀架构设计规范

> **规范版本**：v2.0  
> **创建日期**：2026-10-01  
> **更新日期**：2026-10-01（重大升级：由静态子智能体类演进为动态子智能体运行时 Dynamic Sub-Agent Runtime）  
> **目标分支**：`feat/multi-agent`  
> **状态**：方案设计中（待确认后实施编码）  
> **责任范围**：`server/agent/subagents/`、`server/agent/tools_subagent.py`、`server/agent/tools_wiki.py`、`server/service/wiki_store.py`、`server/agent/core.py`、`tests/test_subagents.py`

---

## 1. 背景与核心诉求

### 1.1 现状痛点
在 `s_agent` 跑通基础三栏工作台并具备腾讯股票量化、SQLite 结构化数据存储与 Tavily 全网搜索后，当前采用的单体 ReAct Agent（`server/agent/core.py`）在面对复杂的深度投资研报任务时面临明显瓶颈：
1. **上下文爆炸与注意力稀释（Context Bloat & Attention Dilution）**：
   - 进行一次深度投研往往需要遍历全网 5~15 篇新闻研报与数十个财报指标。海量未经清洗的原始文本（HTML、搜索引擎摘要、长篇研报）直接充斥主会话，迅速消耗 Context Window（Token 暴涨），并导致模型在多轮对话后遗忘早期核心约束。
2. **多重角色认知混淆（Role Confusion）**：
   - 单一 Agent 既负责面向用户的需求沟通，又负责底层网页爬取清洗，还要编写 Python 脚本严谨计算三张财务报表，最后还要兼顾首席分析师的宏篇巨著与客观风险审查。角色过多导致算术心算幻觉、分析浅尝辄止或格式混乱。
3. **“知识不累积、每次从零开始”（RAG 的固有弊端）**：
   - 传统 RAG 仅依赖临时的向量片段切片，查询结束后知识随会话销毁。当用户上一次调研了“伊利股份生鲜乳周期”，下一次询问“蒙牛与伊利成本对比”时，Agent 无法站在前一次研究的肩膀上，依然消耗大量 Token 重新去外网盲搜。
4. **硬编码静态子智能体的局限性（Hardcoded Sub-Agents Limitation）**：
   - 若在代码中写死固定几个子智能体类（如仅有 `research_analyst` 和 `financial_modeler`），无法应对真实世界千变万化的垂直需求（如：白酒批价与渠道库存调研、光伏逆变器出口海关数据跟踪、破产重整法律风险审查等）。必须赋予系统动态按需生成任意专家的能力。

### 1.2 架构目标
- **动态子智能体运行时（Dynamic Sub-Agent Runtime / JIT Sub-Agent）**：
  - 主 Agent 像调用普通工具一样调用统一的委派工具 `delegate_task`；
  - 调用时，主 Agent 自主指定子智能体的**专属角色定义（Role）**、**详细任务要求（Instruction）**，并**动态授权其可用工具集（Allowed Tools Sandboxing）**；
  - 子智能体在全新、干净的独立上下文沙箱中执行，完成后向主 Agent 提交结构化事实底稿并销毁子上下文，主会话零污染；
- **前后端协议无缝兼容**：
  - 采用 **Tool-based Sub-Agent** 模式，完全复用现有 Redis + SSE 事件流（`ToolCallEvent` / `ToolResultEvent`）与 MateChat 前端三栏交互体系，无需改造前端网络协议；
- **LLM Wiki 范式知识沉淀**：
  - 引入 Andrej Karpathy 提出的 **LLM Wiki 架构**，子智能体在完成调研和测算后，主动将非标的定性认知、行业逻辑、竞争格局与分析底稿编译沉淀为互联的 Markdown 维基网络，实现**跨会话的知识复利增长**；
- **自适应任务主题命名交付**：
  - 严禁机械套用模板名，主 Agent 严格根据用户具体提问（单标的、同业横向对比、行业宏观、专项测算）自适应生成见名知义的交付研报并落盘工作区。

---

## 2. 总体架构：动态子智能体与双轨存储协同

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MateChat 前端工作台                             │
│       左栏: 任务与工作区  |  中栏: 对话流与待办  |  右栏: 产物与预览     │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ SSE 流式事件 (ToolCall / ToolResult)
┌───────────────────────────────────▼────────────────────────────────────┐
│                  主协调智能体 (Main Orchestrator Agent)                  │
│  - 职责: 意图理解、待办规划(Task*)、动态委派子智能体、综合研报起草、交付落盘 │
│  - 工具集: Read, Write, Edit, calculate, Task*, SQLite*, Wiki*, delegate_task│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 调用 delegate_task(role, instruction, tools)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             动态子智能体运行时 (Dynamic Sub-Agent Runtime)               │
│                                                                        │
│   ┌───────────────────────────┐      ┌───────────────────────────┐     │
│   │   按需生成的动态子智能体 A   │      │   按需生成的动态子智能体 B   │     │
│   │   (例: 生鲜乳产业链调研员)    │      │   (例: DCF贴现估值精算师)   │     │
│   ├───────────────────────────┤      ├───────────────────────────┤     │
│   │ • 注入: Research底座 +    │      │ • 注入: Finance底座 +     │     │
│   │         主Agent动态指令    │      │         主Agent动态指令    │     │
│   │ • 沙箱工具: web_search,   │      │ • 沙箱工具: python_calc,  │     │
│   │            wiki_tools     │      │            finance_db     │     │
│   │ • 独立生命周期: 阅后即焚  │      │ • 独立生命周期: 阅后即焚  │     │
│   │ • 结果: 向主Agent提交底稿 │      │ • 结果: 向主Agent提交底稿 │     │
│   └─────────────┬─────────────┘      └─────────────┬─────────────┘     │
└─────────────────┼──────────────────────────────────┼───────────────────┘
                  │                                  │
                  └─────────────────┬────────────────┘
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

## 3. 动态子智能体委派工具设计：`delegate_task`

不再写死静态子智能体类，而是向主 Agent 暴露一个通用的、具备元管理能力的调度工具：`delegate_task`。

### 3.1 统一工具契约（Tool Schema）

```python
def delegate_task(
    role: str,
    instruction: str,
    allowed_tools: list[str],
    base_template: str = "general",
    persist_to_wiki: bool = True,
) -> str:
    """
    动态生成并委派一个具有专属角色和限定工具集的子智能体（Sub-Agent）去执行专业子任务。
    子智能体拥有完全隔离的上下文，执行完毕后向主智能体汇报结构化成果。

    参数:
        role: 子智能体的专业角色定义（如："资深乳品行业调研员"、"CPA财务精算与估值建模师"、"红队风险审查员"）
        instruction: 主 Agent 下达的具体任务目标、分析范围与交付要求
        allowed_tools: 授权该子智能体使用的工具名称列表或工具组别名（见下方支持列表）
        base_template: 基础底座模板类型，可选值:
                       - "research": 适合搜索、研报解读与定性分析
                       - "finance": 适合数据建模、报表核算与公式计算
                       - "general": 通用分析与代码任务
                       - "reviewer": 批判性审查与逻辑挑刺
        persist_to_wiki: 是否授权子智能体将高价值认知与测算底稿自动写入本地投研维基 data/wiki/（默认为 True）
    返回:
        子智能体完成任务后的完整结构化分析报告与事实底稿。
    """
```

### 3.2 双层 Prompt 组装架构

每个被动态唤起的 Sub-Agent，其 System Prompt 由两层拼接而成：

$$\text{Sub-Agent System Prompt} = \text{Base Template Prompt (底层基座)} + \text{Dynamic Intent Prompt (主 Agent 注入)}$$

1. **底层基座模板（Base Template Prompt）**：
   - 固化系统安全边界、排版规范（GFM）、共享工作区目录（`workspace_dir`）；
   - 固化核心纪律（严禁心算、Python 计算使用 f-string 规避 `%` 语法错误、必须查阅本地维基优先等）；
   - 固化“向主 Agent 提交汇报”的协议：不直接面对终端用户，在完成任务后必须输出结构化、高密度的事实底稿。
2. **动态意图提示（Dynamic Intent Prompt）**：
   - 注入主 Agent 传入的 `role`（如：“你现在扮演资深乳品行业分析师...”）；
   - 注入主 Agent 传入的 `instruction`（具体标的、核心调研问题、需要测算的财务指标）。

### 3.3 预置基础底座模板（Base Templates）

系统提供 4 个开箱即用的专业模板：
- **`research`（调研专家模板）**：注重信源真实性、多源交叉验证、事实与观点分离、优先查阅维基并沉淀新认知；
- **`finance`（财务估值模板）**：注重会计勾稽关系严密性、代码实测（Python / calculate）、指标落库 SQLite `stock_financial_metrics`、估值敏感性情景分析；
- **`reviewer`（红队反思模板）**：站在反方空头视角挑刺、查找潜在商誉减值、大客户依赖与应收账款恶化风险；
- **`general`（通用专家模板）**：通用分析、代码脚本调试与数据处理。

### 3.4 动态工具沙箱授权（Tool Sandboxing & Presets）

为了防止主 Agent 记不住近 30 个工具的具体拼写，运行时支持**工具组别名（Presets）**与**单个具体工具**混用：

| 工具组别名 (Preset) | 包含的底层工具 | 典型适用场景 |
| :--- | :--- | :--- |
| `web_search` | `mcp__tavily__tavily-search`, `mcp__tavily__tavily-extract` | 全网深度调研、要闻检索、公告抓取 |
| `stock_market` | `stock_quote`, `stock_kline`, `stock_minute`, `stock_handicap`, `stock_batch_quotes`, `market_index_overview` | 实时行情、历史复权 K 线、分时量价、大单盘口 |
| `finance_db` | `finance_overview`, `finance_watchlist`, `finance_record_metric`, `sqlite_query` | 本地 SQLite 结构化指标库查询与测算事实落库 |
| `python_calc` | `Bash` (受限白名单 Python), `calculate` | 报表穿透核算、DCF 估值测算、敏感性分析 |
| `wiki_tools` | `wiki_query`, `wiki_read`, `wiki_save_page` | LLM Wiki 知识库检索与定性底稿沉淀 |
| `file_io` | `Read`, `Write`, `Edit`, `Glob` | 工作区文件阅读与代码处理 |

**沙箱机制**：Sub-Agent 初始化时，运行时通过 `ToolResolver` 仅将 `allowed_tools` 列表中指定的工具绑定给该 Sub-Agent，其余无关工具完全不可见。

### 3.5 运行时安全防线（Anti-Recursion & Fault-Tolerance）

1. **防递归死循环（Anti-Recursion Guard）**：
   - 在构建 Sub-Agent 的可用工具库时，**强制剥离 `delegate_task` 工具**；
   - 严格限定嵌套调用深度 $\text{depth} = 1$，仅主 Agent 拥有委派权，杜绝套娃与资源耗尽。
2. **执行上限与超时保护（Execution Limits）**：
   - 默认超时限制 120 秒，最大推理轮数 `max_iters = 8`；
   - 若执行意外中断或超时，安全捕获异常并返回当前已提取的阶段性结论，保证主 Agent 不被阻塞挂死。

---

## 4. LLM Wiki 投研知识沉淀体系设计

本体系深度融合 Andrej Karpathy 的经典设计与学术界“持续知识编译（Continual Knowledge Compilation）”范式。

### 4.1 三层知识结构

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

### 4.2 导航与审计双核心文件

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

### 4.3 Sub-Agent 的维基闭环操作

Sub-Agent 在执行任务时遵循三大标准操作：

| 操作 | 触发场景 | Sub-Agent 具体执行行为 |
| :--- | :--- | :--- |
| **Query（查阅在先）** | 接收到调研或建模任务时 | 先调用 `wiki_query` 或查阅 `data/wiki/index.md`，若已有该行业或标的的历史维基页面，直接读取吸纳已有结论，仅对“增量未知部分”向外网检索或重新测算。 |
| **Ingest（编译入库）** | 完成深度分析并产出高置信度结论时 | 调用 `wiki_save_page` 将提炼出的逻辑写入或追加到对应页面；自动向 `index.md` 注册条目；自动在 `log.md` 追加记录。 |
| **Lint（一致性审计）** | 发现新数据与旧维基结论相悖时 | 当最新财报证实原先预测失误时，按照“内容递增原则”保留旧推演，追加标注 `> ⚠️ 2026-10 修正：[修正原因]`，保持认知演进可追溯。 |

---

## 5. 详细模块与类设计

```
server/
├── agent/
│   ├── core.py                   # 主 Agent 构建工厂（注册 delegate_task 与 wiki 工具、优化主 Prompt）
│   ├── subagents/                # [新增] 动态子智能体套件目录
│   │   ├── __init__.py           # 导出公共类
│   │   ├── runner.py             # SubAgentRunner: 隔离上下文容器与短命生命周期执行器
│   │   ├── templates.py          # 预设基础模板库 (research, finance, reviewer, general)
│   │   └── tool_resolver.py      # 工具白名单解析器 (将 Preset 展开为具体工具实例)
│   ├── tools_subagent.py         # 将 delegate_task 封装为 FunctionTool
│   └── tools_wiki.py             # 暴露给 Agent 的 Wiki 原生工具 (wiki_query, wiki_read, wiki_save_page)
└── service/
    ├── finance_db.py             # 已有的 SQLite 结构化数据服务
    └── wiki_store.py             # [新增] LLM Wiki 底层存储管理器（原子读写、索引维护、日志追加）
```

### 5.1 `server/agent/subagents/runner.py` 核心实现骨架

```python
"""
动态子智能体运行时调度器。
"""
import asyncio
import logging
from typing import Any, List
from agentscope.agent import Agent, ContextConfig, ModelConfig
from agentscope.tool import Toolkit
from agentscope.state import AgentState

logger = logging.getLogger(__name__)

class DynamicSubAgentRunner:
    """动态子智能体运行时执行容器"""

    def __init__(
        self,
        role: str,
        system_prompt: str,
        toolkit: Toolkit,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_iters: int = 8,
    ):
        self.role = role
        self.system_prompt = system_prompt
        self.toolkit = toolkit
        self.model_name = model_name
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_iters = max_iters

    async def execute(self, instruction: str) -> str:
        """
        在全新、隔离的 Agent 上下文中执行任务，并在完成后安全提取结果。
        """
        # 1. 组装短命 Agent 实例，绑定隔离的 AgentState 与专属 Toolkit
        # 2. 施加 asyncio.wait_for 超时保护
        # 3. 运行多轮 ReAct 推理与工具调用
        # 4. 提取最后一轮结构化成果，销毁子上下文，返回结果
        ...
```

---

## 6. 主 Agent 协同调度与自适应命名交付

### 6.1 多智能体标准协同 SOP

在主 Agent 的 `SYSTEM_PROMPT_TEMPLATE` 中固化协同调度工作流：

1. **第 1 步：大纲规划**  
   面对复杂任务，首先调用 `TaskCreate` 创建推进清单（如：1. 行业与公司情报搜集 2. 财务报表穿透建模 3. 综合研报撰写 4. 交付落盘）；
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

## 7. 测试策略与验收标准

### 7.1 单元测试（`tests/test_subagents.py` & `tests/test_wiki_store.py`）
- **WikiStore 单元测试**：
  - 维基目录自动初始化、`SCHEMA.md`、`index.md` 与 `log.md` 骨架验证；
  - `save_page` 写入同时自动更新 `index.md` 索引与追加 `log.md` 日志；
  - `query_wiki` 与 `read_page` 精准检索；
- **ToolResolver 单元测试**：
  - 测试工具组别名（`web_search`, `python_calc` 等）正确展开为底层工具列表；
  - 测试防递归机制（Sub-Agent 无法解析获取 `delegate_task` 工具）；
- **DynamicSubAgentRunner 独立执行测试**：
  - 测试动态注入 Prompt 与工具沙箱执行；
  - 测试超时（Timeout）与异常兜底，确保主 Agent 永不挂死。

### 7.2 端到端投研实战验收
- **场景 1：乳制品行业两巨头横向对比**
  - 用户提问：“对比伊利与蒙牛的自由现金流、上游原奶周期影响及海外布局，生成对比研报”；
  - 验证主 Agent 动态派遣调研员与财务建模师；
  - 验证工作区生成符合主题命名的交付文件：`乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`；
  - 验证事实分别沉淀至 `data/wiki/entities/` 与 `data/wiki/industries/`；
  - 验证主会话 Token 相比单体 Agent 降低 50% 以上。
- **场景 2：次轮会话增量提问**
  - 用户新任务：“伊利与新乳业相比如何？”；
  - 验证 Sub-Agent **直接读取维基中已有的伊利页面**，免除重复外网检索。

---

## 8. 实施任务分解（待确认后执行）

- [ ] **Task 1**：实现 `server/service/wiki_store.py`（LLM Wiki 底层存储管理器、索引自动维护与日志审计流）；
- [ ] **Task 2**：实现 `server/agent/tools_wiki.py`（封装 `wiki_query`, `wiki_read`, `wiki_save_page` 等原生工具）；
- [ ] **Task 3**：实现 `server/agent/subagents/templates.py`（预设 base templates: research, finance, reviewer, general）；
- [ ] **Task 4**：实现 `server/agent/subagents/tool_resolver.py`（工具组别名映射与沙箱白名单解析，剥离 `delegate_task`）；
- [ ] **Task 5**：实现 `server/agent/subagents/runner.py`（DynamicSubAgentRunner 动态生命周期执行容器）；
- [ ] **Task 6**：实现 `server/agent/tools_subagent.py`（封装 `delegate_task` 为主 Agent 可调用的 FunctionTool）；
- [ ] **Task 7**：优化 `server/agent/core.py`（注册新工具、精简主 Prompt、注入动态委派协同 SOP 与自适应命名规范）；
- [ ] **Task 8**：编写单元测试（`tests/test_wiki_store.py`, `tests/test_subagents.py`）并完成全量回归与实战验证。
