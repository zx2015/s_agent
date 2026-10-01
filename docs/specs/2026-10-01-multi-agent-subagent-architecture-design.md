# Multi-Agent 子智能体协同架构设计规范

> **规范版本**：v1.0  
> **创建日期**：2026-10-01  
> **目标分支**：`feat/multi-agent`  
> **状态**：方案设计中（待确认后实施编码）  
> **责任范围**：`server/agent/subagents/`、`server/agent/tools_subagent.py`、`server/agent/core.py`、`tests/test_subagents.py`

---

## 1. 背景与核心诉求

### 1.1 现状痛点
在 `s_agent` 跑通基础三栏工作台并具备腾讯股票量化、SQLite 结构化数据存储与 Tavily 全网搜索后，当前采用的单体 ReAct Agent（`server/agent/core.py`）在面对复杂的深度投资研报任务时面临明显瓶颈：
1. **上下文爆炸与注意力稀释（Context Bloat & Attention Dilution）**：
   - 进行一次深度投研往往需要遍历全网 5~15 篇新闻研报与数十个财报指标。海量未经清洗的原始文本（HTML、搜索引擎摘要、长篇研报）直接充斥主会话，迅速消耗 Context Window（Token 暴涨），并导致模型在多轮对话后遗忘早期核心约束。
2. **多重角色认知混淆（Role Confusion）**：
   - 单一 Agent 既负责面向用户的需求沟通，又负责底层网页爬取清洗，还要编写 Python 脚本严谨计算三张财务报表，最后还要兼顾首席分析师的宏篇巨著与客观风险审查。角色过多导致算术心算幻觉、分析浅尝辄止或格式混乱。
3. **主提示词臃肿与工具选择精度下降**：
   - 单 Agent 挂载近 30 个工具，主 System Prompt 混杂了工作区规则、文件读写、计算规范、数据库 Schema、量化 SOP 等，降低了大模型判断与调优工具调用的精确度。

### 1.2 架构目标
- **上下文深度解耦**：将网络爬取、数据清洗、Python 报表核算等重型中间交互完全隔离在子智能体独立的短命生命周期（ephemeral context）中，主会话只保留精炼的高密度事实底稿与结论；
- **前后端协议无缝兼容**：采用 **Tool-based Sub-Agent（子智能体即工具）** 模式，主 Agent 像调用普通工具一样委派 Sub-Agent，完全复用现有 Redis + SSE 事件流（`ToolCallEvent` / `ToolResultEvent`）与 MateChat 前端三栏交互体系，无需对前端架构伤筋动骨；
- **共享环境一致性**：所有 Sub-Agent 共享同一任务工作区目录（`workspace_dir`）和底层 SQLite 金融持久化数据库（`finance_db`），支持数据落库跨 Agent 即刻复用。

---

## 2. 核心架构与设计原则

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MateChat 前端工作台                             │
│       左栏: 任务与工作区  |  中栏: 对话流与待办  |  右栏: 产物与预览     │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ SSE 流式事件 (ToolCall / ToolResult)
┌───────────────────────────────────▼────────────────────────────────────┐
│                  主协调智能体 (Main Orchestrator Agent)                  │
│  - 职责: 用户意图识别、待办规划(TaskCreate/Update)、报告合成、交付落盘  │
│  - 工具集: Read, Write, Edit, calculate, Task*, SQLite*, delegate_*   │
└───────────────┬────────────────────────────────────────┬───────────────┘
                │ 调用 (ToolCall)                         │ 调用 (ToolCall)
                ▼                                        ▼
┌───────────────────────────────┐        ┌───────────────────────────────┐
│  资讯研报情报员 (Sub-Agent 1)  │        │  财务量化建模员 (Sub-Agent 2)  │
│  research_analyst             │        │  financial_modeler            │
├───────────────────────────────┤        ├───────────────────────────────┤
│ • 专属 Prompt: 资深行业调研员  │        │ • 专属 Prompt: 严谨CPA/估值师  │
│ • 工具: Tavily, Read, 网页抓取 │        │ • 工具: Python(Bash), SQLite  │
│ • 独立上下文: 阅后即焚(短命)   │        │ • 独立上下文: 调试错误不污染主会话│
│ • 输出: 《核心研报与事实清单》 │        │ • 输出: 《财务事实底稿及指标》 │
└───────────────┬───────────────┘        └───────────────┬───────────────┘
                │                                        │
                └───────────────────┬────────────────────┘
                                    ▼
                ┌────────────────────────────────────────┐
                │   共享存储层 (Shared Storage Layer)     │
                │  - 工作区根目录: {workspace_dir}/      │
                │  - SQLite 数据库: finance_db (WAL)     │
                └────────────────────────────────────────┘
```

### 2.1 设计原则

1. **子智能体作为工具（Agent-as-a-Tool）**：
   - 每个 Sub-Agent 封装为一个标准的 AgentScope `FunctionTool`，具有规范的入参定义（JSON Schema）与清晰的功能描述（Description）；
   - 主 Agent 依据任务需求自主决策何时委派子智能体、委派给谁、传递什么具体问题。
2. **上下文强隔离（Strict Context Isolation）**：
   - Sub-Agent 执行时创建独立的 `Agent` 实例与 `AgentState`；
   - Sub-Agent 在子循环中执行多步 ReAct 思考与工具调用，所有爬虫长文本、Python 试错输出均留在子上下文中；
   - 任务完成后，子智能体提取最终结果作为 `ToolResponse` 返回给主 Agent，子状态销毁，主会话零污染。
3. **最小工具集与专业化 Prompt（Specialized Toolkits & Roles）**：
   - 严禁将所有工具挂给 Sub-Agent。调研员只能搜索与阅读，建模员只能运行计算与存取数据库，保证职责单一、运行可预测。
4. **共享工作区与持久化数据库（Shared Context & DB）**：
   - Sub-Agent 共享主任务的 `workspace_dir`，允许建模员或调研员将大体积原始数据或中间图表写入工作区，或将核心指标持久化到 `finance_db` 中的 `stock_financial_metrics`，主 Agent 可无缝读取。
5. **健壮的超时与异常兜底（Timeout & Fault-Tolerance）**：
   - 每个 Sub-Agent 调用设置超时时间（如 120 秒）与最大迭代轮数（`max_iters = 6~10`），防止子智能体陷入死循环或耗尽系统资源。

---

## 3. 首批 Sub-Agent 规格与接口设计

第一阶段优先实现投研业务中最关键、上下文消耗最大的两个子智能体：

### 3.1 资讯研报情报员（`research_analyst`）

- **角色定位**：资深行业研究员与全网情报侦察员。
- **职责**：
  - 针对指定标的或行业主题，检索全网最新研报、核心催化剂、公司公告、产能扩产、上下游产业链动态与行业周期；
  - 自动过滤垃圾公关稿与重复资讯，交叉对比多方信源；
  - 整理输出高浓度的《核心研报事实与观点摘要》。
- **专属工具集**：
  - `mcp__tavily__tavily-search`（搜索外部权威资讯）
  - `mcp__tavily__tavily-extract`（抽取权威网页正文）
  - `Read`（读取工作区已下载或现有的研报文本）
- **工具入参契约**：
  ```python
  def research_analyst(
      query: str,
      stock_symbol: str = "",
      focus_points: list[str] = None,
  ) -> str:
      """
      委派资讯研报情报员（Sub-Agent）进行全网行业研究、公告检索与核心催化剂挖掘。

      参数:
          query: 调研核心问题（如："分析伊利股份2024年下半年原奶周期的影响及冷饮业务增速"）
          stock_symbol: 股票代码或标的名称（如 "sh600887" 或 "伊利股份"）
          focus_points: 重点调研维度列表（如 ["原奶价格走势", "海外建厂进展", "竞品动向"]）
      返回:
          精炼的高置信度事实清单与研报核心观点（包含信源出处）。
      """
  ```
- **输出交付物示例**：
  ```markdown
  ### 【情报研报精炼底稿】伊利股份
  1. 周期拐点：农业部数据显示生鲜乳均价降至 3.15 元/公斤，上游去产能接近尾声，预计 2025 年下半年供需重回平衡；
  2. 业务亮点：冷饮业务连续多年行业第一，Q2单季实现双位数增长（+13.4%），海外印尼工厂二期投产；
  3. 机构共识：15家券商核心预期净利润复合增速 8%~10%，当前估值隐含悲观预期充分。
  ```

---

### 3.2 财务深度精算与估值建模员（`financial_modeler`）

- **角色定位**：严谨的注册会计师（CPA）与买方量化建模分析师。
- **职责**：
  - 三张表穿透核算（自由现金流 FCF、净利润现金含量、三费比率跨期对比、资产负债结构）；
  - 估值建模测算（DCF 贴现敏感性分析、PE/PB 分位数回测、股息率与回购回报率测算）；
  - 严谨运行 Python 验证，禁止任何形式的心算与估算；
  - 自动将关键测算结果持久化到本地 SQLite 的 `stock_financial_metrics` 事实底稿表中。
- **专属工具集**：
  - `Bash`（限定于运行 Python 脚本进行批量计算、数据清洗与建模）
  - `calculate`（精确数学表达式求值）
  - `sqlite_query`（读取本地已有的历史行情与财务数据）
  - `finance_record_metric`（将核算完成的核心财务事实持久化落库）
- **工具入参契约**：
  ```python
  def financial_modeler(
      stock_symbol: str,
      task_description: str,
      metrics_to_calculate: list[str] = None,
  ) -> str:
      """
      委派财务精算与估值建模员（Sub-Agent）运行 Python 进行报表穿透、比率核算与 DCF 估值测算。

      参数:
          stock_symbol: 股票标的代码（如 "sh600887"）
          task_description: 具体建模要求（如："计算近三年经营现金流/归母净利润比率，并测算若回购上限达到20亿对每股收益的增厚效应"）
          metrics_to_calculate: 需要测算并持久化的核心指标项
      返回:
          严密核算的财务底稿、比率表格及建模结论，所有核心指标均已自动入库 SQLite。
      """
  ```
- **输出交付物示例**：
  ```markdown
  ### 【财务精算事实底稿】sh600887
  | 财务指标 | 2024H1 实测值 | 2023H1 | 同比变动 | 测算口径/说明 |
  | :--- | :--- | :--- | :--- | :--- |
  | 经营现金流 | 97.59 亿元 | 29.66 亿元 | +229.0% | 销售回款加速与存货周转改善 |
  | 现金净利比 | 1.69 | 0.47 | +259.6% | 经营现金流 / 归母净利润(57.59亿) |
  | 销售费用率 | 17.77% | 18.20% | -0.43 pct | 1143.22 / 6433.09 * 100 |
  > 状态: 核心指标已成功同步持久化至 SQLite `stock_financial_metrics` 表。
  ```

---

## 4. 详细模块与类设计

系统文件组织结构：

```
server/agent/
├── core.py                   # 主 Agent 构建工厂（注册 subagent 工具、精简后的主 Prompt）
├── subagents/                # [新增] 子智能体套件目录
│   ├── __init__.py           # 导出子智能体工具
│   ├── base.py               # SubAgent 运行框架与基础调度基类
│   ├── research.py           # 资讯研报情报员实现
│   └── fin_modeler.py        # 财务估值建模员实现
├── tools_subagent.py         # [新增] 将 Sub-Agent 包装为 AgentScope FunctionTool
```

### 4.1 `server/agent/subagents/base.py` 核心实现逻辑

```python
"""
Sub-Agent 执行基础设施。

负责在收到主 Agent 的工具调用时，安全、快速地生成隔离的短命 Agent，
执行多轮 ReAct 并在完成后提取有效产物，附带超时控制与异常截获。
"""
import asyncio
from typing import Any, List
from agentscope.agent import Agent, ContextConfig, ModelConfig
from agentscope.tool import Toolkit
from agentscope.state import AgentState
from agentscope.message import Msg

class SubAgentRunner:
    """Sub-Agent 统一运行器"""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        toolkit: Toolkit,
        model_name: str = None,
        base_url: str = None,
        max_iters: int = 8,
        timeout_seconds: float = 120.0,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.toolkit = toolkit
        self.model_name = model_name
        self.base_url = base_url
        self.max_iters = max_iters
        self.timeout_seconds = timeout_seconds

    async def run(self, user_instruction: str) -> str:
        """
        在全新、隔离的 Agent 上下文中执行任务并返回紧凑结果。
        """
        # 1. 动态装配独立短命 Agent
        # 2. 注入专属提示词与精简工具集
        # 3. 带超时的 asyncio.wait_for 运行
        # 4. 提取最后一轮有效回复文本返回
        ...
```

### 4.2 工具包装层 `server/agent/tools_subagent.py`

通过标准 `FunctionTool` 包装，向主 Agent 暴露：
1. `research_analyst`
2. `financial_modeler`

在 `server/agent/core.py` 中：
```python
# 将 Sub-Agent 工具与本地基础工具（文件操作、数据库查询、大纲规划等）一并注册入主 Agent
subagent_tools = build_subagent_tools(
    workspace_dir=workspace_dir,
    model_name=model_name,
    base_url=base_url,
    mcp_tools=tavily_tools,
)
for tool in subagent_tools:
    toolkit.register(tool)
```

---

## 5. 主 Agent（Main Orchestrator）的提示词重构

在引入 Sub-Agent 后，主 Agent 的 `SYSTEM_PROMPT_TEMPLATE` 将进行大幅精简与职责升级：

1. **移除细节负担**：
   - 移除非必要的海量细节指导（如复杂的 Python 格式化转义说明、冗长的全网爬虫细节等，这些已内聚在子智能体提示词中）；
2. **新增协同调度 SOP（Delegation SOP）**：
   - 指导主 Agent 在面对深度任务时遵循标准投研工序：
     - **步骤 1（规划）**：调用 `TaskCreate` 创建四步待办（1. 情报搜集 2. 财务建模 3. 研报起草 4. 归档交付）；
     - **步骤 2（外包搜集）**：委派 `research_analyst` 获取行业最新周期与公司要闻；
     - **步骤 3（外包核算）**：委派 `financial_modeler` 计算关键财务指标并沉淀事实底稿；
     - **步骤 4（合成落盘）**：汇总所有子智能体成果，调用 `Write` 生成最终《XXX投资价值深度分析.md》交付物，并调用 `TaskUpdate` 标记完成。

---

## 6. 与现有系统与前端的契约兼容性

1. **Redis 状态机无感知**：
   - Sub-Agent 的调用在外层对主 Agent 来说就是一次常规的异步工具调用；
   - 主 Agent 发送 `ToolCallBlock(name="research_analyst", ...)`，接收 `ToolResultBlock(output="...")`，原有的 Redis SSE 状态机与前端完全兼容。
2. **前端界面自然呈现**：
   - 前端对话流中清晰呈现 Agent 调用了「`research_analyst`（资讯研报情报员）」与「`financial_modeler`（财务量化建模员）」的折叠卡片；
   - 用户可随时展开查看情报员抓取的关键线索与精算师核算的底稿表格；
   - 极大地增强了专业投研团队分工协作的视觉与体验真实感。
3. **安全与权限继承**：
   - Sub-Agent 运行在安全模式下时，写操作严格限制在当前任务工作区内，继承主 Agent 的安全白名单配置。

---

## 7. 测试策略与验收标准

### 7.1 单元测试（`tests/test_subagents.py`）
- **SubAgent 独立测试**：
  - 测试 `research_analyst` 工具包装、入参校验与 Mock 回复；
  - 测试 `financial_modeler` Python 计算与 SQLite `stock_financial_metrics` 落库联动；
- **超时与容错测试**：
  - 测试子智能体在遇到异常或超时时的安全降级机制，确保主 Agent 不会挂死。

### 7.2 端到端投研实战验收
- 场景测试：在前端输入：“对伊利股份进行深度投资分析，包括最新行业生鲜乳周期、核心财务比率与估值评估，生成交付报告”；
- 验收指标：
  1. 主 Agent 成功分发调用 `research_analyst` 与 `financial_modeler`；
  2. 主会话 Token 消耗相比纯单体 Agent 降低 **50% 以上**；
  3. 中间复杂的网页与 Python 计算未出现在主会话中，但最终生成的交付报告详尽专业；
  4. SQLite 事实底稿成功沉淀。

---

## 8. 实施任务拆解（待确认后执行）

- [ ] **Task 1**：创建 `server/agent/subagents/base.py`，实现 `SubAgentRunner` 基础调度与短命 Agent 容器；
- [ ] **Task 2**：创建 `server/agent/subagents/research.py`，封装资讯研报子智能体；
- [ ] **Task 3**：创建 `server/agent/subagents/fin_modeler.py`，封装财务精算与估值建模子智能体；
- [ ] **Task 4**：创建 `server/agent/tools_subagent.py`，完成 FunctionTool 包装；
- [ ] **Task 5**：改造 `server/agent/core.py` 接入子智能体工具，优化主 Agent 协同提示词；
- [ ] **Task 6**：编写 `tests/test_subagents.py`，完成测试闭环与实战校验。
