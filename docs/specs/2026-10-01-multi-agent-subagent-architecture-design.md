# Multi-Agent 协同与 LLM Wiki 知识沉淀架构设计规范

> **规范版本**：v1.1  
> **创建日期**：2026-10-01  
> **更新日期**：2026-10-01（深度集成 Andrej Karpathy LLM Wiki 知识沉淀范式）  
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

### 1.2 架构目标
- **上下文深度解耦**：将网络爬取、数据清洗、Python 报表核算等重型中间交互完全隔离在子智能体独立的短命生命周期（ephemeral context）中，主会话只保留精炼的高密度事实底稿与结论；
- **前后端协议无缝兼容**：采用 **Tool-based Sub-Agent（子智能体即工具）** 模式，主 Agent 像调用普通工具一样委派 Sub-Agent，完全复用现有 Redis + SSE 事件流（`ToolCallEvent` / `ToolResultEvent`）与 MateChat 前端三栏交互体系，无需对前端架构伤筋动骨；
- **LLM Wiki 范式知识沉淀**：引入 Andrej Karpathy 提出的 **LLM Wiki 架构**，让 Sub-Agent 在完成调研和测算后，主动将非标的定性认知、行业逻辑、竞争格局与分析底稿编译沉淀为互联的 Markdown 维基网络，实现**跨会话的知识复利增长**；
- **双轨制存储协同**：定量硬数据存入 SQLite（`finance_db`），定性研究逻辑与事实存入维基（`data/wiki/`），共同构成强大的投研底座。

---

## 2. 总体架构：Multi-Agent 与 LLM Wiki 双轨协同

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MateChat 前端工作台                             │
│       左栏: 任务与工作区  |  中栏: 对话流与待办  |  右栏: 产物与预览     │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ SSE 流式事件 (ToolCall / ToolResult)
┌───────────────────────────────────▼────────────────────────────────────┐
│                  主协调智能体 (Main Orchestrator Agent)                  │
│  - 职责: 需求识别、待办编排(Task*)、调度子智能体、综合报告起草、交付落盘 │
│  - 工具集: Read, Write, Edit, calculate, Task*, SQLite*, Wiki*, delegate*│
└───────────────┬────────────────────────────────────────┬───────────────┘
                │ 委派 (ToolCall)                         │ 委派 (ToolCall)
                ▼                                        ▼
┌───────────────────────────────┐        ┌───────────────────────────────┐
│  资讯研报情报员 (Sub-Agent 1)  │        │  财务量化建模员 (Sub-Agent 2)  │
│  research_analyst             │        │  financial_modeler            │
├───────────────────────────────┤        ├───────────────────────────────┤
│ • 专属 Prompt: 资深行业调研员  │        │ • 专属 Prompt: 严谨CPA/估值师  │
│ • 工具: Tavily, Read, Wiki*   │        │ • 工具: Python(Bash), SQLite, │
│ • 独立上下文: 阅后即焚(短命)   │        │   calculate, Wiki*            │
│ • 产出: 研报事实摘要          │        │ • 独立上下文: 调试错误不污染主会话│
│ • 沉淀: 写入行业/实体维基页面  │        │ • 产出: 财务事实底稿及建模指标  │
│                              │        │ • 沉淀: 写入指标库与专题分析维基│
└───────────────┬───────────────┘        └───────────────┬───────────────┘
                │                                        │
                └───────────────────┬────────────────────┘
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

## 3. LLM Wiki 投研知识沉淀体系设计

本体系深度融合 Andrej Karpathy 的经典设计与学术界“持续知识编译（Continual Knowledge Compilation）”范式。

### 3.1 三层知识结构

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

### 3.2 导航与审计双核心文件

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

### 3.3 Sub-Agent 的维基闭环操作

Sub-Agent 在执行任务时遵循三大标准操作：

| 操作 | 触发场景 | Sub-Agent 具体执行行为 |
| :--- | :--- | :--- |
| **Query（查阅在先）** | 接收到调研或建模任务时 | 先调用 `wiki_query` 或查阅 `data/wiki/index.md`，若已有该行业或标的的历史维基页面，直接读取吸纳已有结论，仅对“增量未知部分”向外网检索或重新测算。 |
| **Ingest（编译入库）** | 完成深度分析并产出高置信度结论时 | 调用 `wiki_save_page` 将提炼出的逻辑写入或追加到对应页面；自动向 `index.md` 注册条目；自动在 `log.md` 追加记录。 |
| **Lint（一致性审计）** | 发现新数据与旧维基结论相悖时 | 当最新财报证实原先预测失误时，按照“内容递增原则”保留旧推演，追加标注 `> ⚠️ 2026-10 修正：[修正原因]`，保持认知演进可追溯。 |

---

## 4. Sub-Agent 规格与接口设计

### 4.1 资讯研报情报员（`research_analyst`）

- **角色定位**：资深行业研究员与全网情报侦察员。
- **专属工具集**：
  - `mcp__tavily__tavily-search`（搜索外部权威资讯）
  - `mcp__tavily__tavily-extract`（抽取权威网页正文）
  - `wiki_query`、`wiki_read`、`wiki_save_page`（维基存取）
  - `Read`（读取工作区已下载或现有的研报文本）
- **工具调用契约**：
  ```python
  def research_analyst(
      query: str,
      stock_symbol: str = "",
      focus_points: list[str] = None,
      persist_to_wiki: bool = True,
  ) -> str:
      """
      委派资讯研报情报员进行全网行业研究、公告检索、催化剂挖掘，并沉淀到投研维基。

      参数:
          query: 调研核心问题（如："分析伊利股份2024年下半年原奶周期的影响及冷饮业务增速"）
          stock_symbol: 股票代码或标的名称（如 "sh600887" 或 "伊利股份"）
          focus_points: 重点调研维度列表
          persist_to_wiki: 是否将调研成果自动编译入 data/wiki/（默认为 True）
      返回:
          精炼的高置信度事实清单与研报核心观点，并注明已沉淀的维基页面路径。
      """
  ```

---

### 4.2 财务深度精算与估值建模员（`financial_modeler`）

- **角色定位**：严谨的注册会计师（CPA）与买方量化建模分析师。
- **专属工具集**：
  - `Bash`（限定于运行 Python 脚本进行批量计算、数据清洗与建模）
  - `calculate`（精确数学表达式求值）
  - `sqlite_query`、`finance_record_metric`（SQLite 事实库交互）
  - `wiki_read`、`wiki_save_page`（维基专题底稿沉淀）
- **工具调用契约**：
  ```python
  def financial_modeler(
      stock_symbol: str,
      task_description: str,
      metrics_to_calculate: list[str] = None,
      persist_to_wiki: bool = True,
  ) -> str:
      """
      委派财务精算与估值建模员运行 Python 进行报表穿透、比率核算、DCF 估值，
      并将指标落库 SQLite，将详细测算底稿沉淀至 data/wiki/analyses/。

      参数:
          stock_symbol: 股票标的代码（如 "sh600887"）
          task_description: 具体建模要求（如："计算近三年经营现金流/归母净利润比率，并测算回购增厚效应"）
          metrics_to_calculate: 需要测算并持久化的核心指标项
          persist_to_wiki: 是否将测算底稿写入维基（默认为 True）
      返回:
          严密核算的财务底稿、比率表格及建模结论。
      """
  ```

---

## 5. 详细模块与类设计

```
server/
├── agent/
│   ├── core.py                   # 主 Agent 构建工厂（注册 subagent 工具、维基工具、精简后的主 Prompt）
│   ├── subagents/                # 子智能体套件目录
│   │   ├── __init__.py           # 导出子智能体
│   │   ├── base.py               # SubAgentRunner 调度框架与隔离短命生命周期
│   │   ├── research.py           # 资讯研报情报员实现
│   │   └── fin_modeler.py        # 财务估值建模员实现
│   ├── tools_subagent.py         # 将 Sub-Agent 包装为 AgentScope FunctionTool
│   └── tools_wiki.py             # 暴露给 Agent 的 Wiki 原生工具接口
└── service/
    ├── finance_db.py             # 已有的 SQLite 结构化数据服务
    └── wiki_store.py             # [新增] LLM Wiki 底层存储管理器（原子读写、索引维护、日志追加）
```

### 5.1 `server/service/wiki_store.py` 核心职责

封装对 `data/wiki/` 目录的安全操作，保证并发与一致性：
- `initialize_wiki()`：若目录不存在，自动创建目录骨架、`SCHEMA.md`、空的 `index.md` 与 `log.md`；
- `query_wiki(keyword, category=None)`：首先在 `index.md` 中进行精准目录匹配，必要时对 `.md` 文本进行轻量关键词定位；
- `read_page(relative_path)`：读取指定页面内容，返回 Markdown 字符串；
- `save_page(category, page_name, content, summary, author)`：
  - 写入对应 `entities/`、`industries/` 或 `analyses/` 文件；
  - 自动更新 `index.md` 对应分类目录中的条目与摘要；
  - 自动向 `log.md` 追加一条审计记录；
- `append_log(author, action, message)`：直接向 `log.md` 写入自定义事件。

### 5.2 `server/agent/subagents/base.py` 调度执行器

```python
class SubAgentRunner:
    """Sub-Agent 隔离运行器"""

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
        ...

    async def run(self, instruction: str) -> str:
        """
        1. 实例化全新的短命 Agent 与 AgentState；
        2. 注入专业 Prompt 与最小专用工具集；
        3. 通过 asyncio.wait_for 施加超时保护；
        4. 运行多轮 ReAct，完成后提取最终有效文本并销毁子上下文；
        5. 遇异常或超时安全降级，返回清晰错误提示。
        """
```

---

## 6. 主 Agent 协同调度与提示词优化

在主 Agent 的 `SYSTEM_PROMPT_TEMPLATE` 中引入标准 **多智能体投研协作 SOP**：

1. **第 1 步：大纲规划**  
   调用 `TaskCreate` 创建四步清单：
   - 1. 情报侦察与行业维基检索
   - 2. 财务报表穿透与量化建模
   - 3. 综合投研报告撰写
   - 4. 维基归档与工作区产物交付
2. **第 2 步：情报委派**  
   调用 `research_analyst`，指定调研主题与关注维度。情报员将先行检索本地维基，再查外网，并自动将核心认知写回 `data/wiki/`；
3. **第 3 步：财务精算**  
   调用 `financial_modeler`，指定测算口径与股票代码。建模员运行 Python 计算指标并存入 SQLite，将详细底稿沉淀至维基；
4. **第 4 步：自适应命名与交付落盘（Dynamic Artifact Generation）**  
   - 主 Agent 提取两名子智能体的高质量事实底稿，撰写最终的深度研报；
   - **自适应主题命名规范（严禁死板套用模板名）**：必须根据用户的具体问题意图、研究对象与分析类型，动态确定见名知义的交付文件名，使用 `Write` 工具落盘到 `{workspace_dir}/` 根目录：
     - **单标的综合研报**：`{workspace_dir}/<标的名称>_深度投资分析.md`（如 `伊利股份_深度投资分析.md`）；
     - **同业横向对比**：`{workspace_dir}/<行业名称>_<对比标的>_横向对比与竞争格局.md`（如 `乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`）；
     - **行业/宏观专题**：`{workspace_dir}/<行业或赛道>_<研究主题>.md`（如 `生鲜乳行业_供需周期与成本拐点展望.md`）；
     - **专项财务/估值测算**：`{workspace_dir}/<标的名称>_<报告期或主题>_专项财务测算.md`（如 `伊利股份_2024H1_自由现金流与回购增厚测算.md`）；
   - 文件落盘后，会自动实时出现在前端工作台右侧「产物/预览」面板，支持在线渲染、目录跳转、新标签独立阅读与下载；
5. **第 5 步：待办更新**  
   调用 `TaskUpdate` 标记任务全部完成。


---

## 7. 测试策略与验收标准

### 7.1 单元测试（`tests/test_subagents.py` & `tests/test_wiki_store.py`）
- **WikiStore 单元测试**：
  - 测试维基目录自动初始化；
  - 测试 `save_page` 写入同时自动更新 `index.md` 与追加 `log.md`；
  - 测试 `query_wiki` 检索命中；
- **SubAgent 独立测试**：
  - 测试 `research_analyst` 工具包装与入参校验；
  - 测试 `financial_modeler` 工具包装与 Python 计算联动；
  - 测试子智能体执行超时（Timeout）与异常兜底，确保主 Agent 不被阻塞挂死。

### 7.2 端到端投研实战验收
- **实测场景**：
  1. 首轮提问：“对伊利股份进行深度投资分析，包括生鲜乳周期、核心财务比率与估值评估，生成交付报告”；
     - 验证两名 Sub-Agent 协同工作；
     - 验证工作区生成完整的 Markdown 交付物；
     - 验证 `data/wiki/` 中成功沉淀了 `sh600887.md` 与生鲜乳行业页面；
     - 验证主会话 Token 相比单 Agent 减少 50% 以上。
  2. 次轮新任务：“对比蒙牛与伊利的成本控制与利润率走势”；
     - 验证 Sub-Agent **直接读取维基中已沉淀的伊利事实**，无需重复全网搜索，显著降低响应延迟与 Token 消耗。

---

## 8. 实施任务分解（待确认后执行）

- [ ] **Task 1**：实现 `server/service/wiki_store.py`（LLM Wiki 存储管理器、索引自动维护与日志流）；
- [ ] **Task 2**：实现 `server/agent/tools_wiki.py`（封装 `wiki_query`, `wiki_read`, `wiki_save_page` 等原生工具）；
- [ ] **Task 3**：实现 `server/agent/subagents/base.py`（SubAgentRunner 调度基座与短命上下文隔离）；
- [ ] **Task 4**：实现 `server/agent/subagents/research.py`（集成 Tavily 与 Wiki 沉淀的资讯情报员）；
- [ ] **Task 5**：实现 `server/agent/subagents/fin_modeler.py`（集成 Python 计算、SQLite 与 Wiki 沉淀的财务建模员）；
- [ ] **Task 6**：实现 `server/agent/tools_subagent.py`（将子智能体包装为主 Agent 可识别的 FunctionTool）；
- [ ] **Task 7**：优化 `server/agent/core.py`（注册新工具、优化主 Agent 协作提示词与调度 SOP）；
- [ ] **Task 8**：编写全量单元测试与实战回归验证（`tests/test_wiki_store.py`, `tests/test_subagents.py`）。
