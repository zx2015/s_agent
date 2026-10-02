# 工作区沙箱化 Glob 检索与工作区专属 Wiki 架构设计规范

> 📌 架构设计规范文档  
> **创建日期**：2026-10-02  
> **状态**：评审中 (In Review)  
> **归档位置**：`docs/specs/2026-10-02-workspace-scoped-glob-and-wiki-design.md`

---

## 1. 需求背景与核心痛点

在多工作区（Workspace）投研系统向“共享资产协同”演进的过程中，发现了两个严重的范围越界与数据共享越权问题：

### 1.1 痛点一：Glob 文件检索越界泄露（全项目代码与跨工作区穿透）
- **现象**：当智能体在某个任务中调用 `Glob` 工具检索文件（如 `Glob(pattern="*.md")` 或 `Glob(pattern="**/*.py")`）时，工具检索了整个 `s_agent` 根目录下的所有内容。
- **根因**：
  1. AgentScope 官方内置的 `Glob` 工具依赖底层 `BackendBase.getcwd()`。在默认的 `LocalBackend` 实现中，`getcwd()` 直接返回宿主主进程的当前工作目录 `os.getcwd()`（即系统仓库根目录 `/media/data/git/s_agent`）。
  2. 当模型不传 `path` 参数或传入相对路径时，底层 `_glob_helper.py` 会从仓库根目录开始递归遍历搜索。
  3. 检索结果不仅混杂了系统的 Python 源代码、测试用例、配置、依赖包，还穿透暴露了**其他独立工作区**的私密文件，造成严重的数据泄露与上下文幻觉。
- **用户要求**：
  > “Glob 在检索文件时，会在 s_agent 整个目录下检索。实际上，检索应该只在当前工作区 workspace 内检索，也不能检索到其他的工作区。”

### 1.2 痛点二：Wiki 全局共享导致知识污染与数据割裂
- **现象**：当前投研知识库维基（`WikiStore`）的存储路径固定在全局的 `data/wiki/` 目录下，所有工作区的所有任务共用这一个维基。
- **根因**：
  1. `server/config.py` 与 `server/service/wiki_store.py` 中写死了全局路径 `data/wiki/`，并通过全局单例 `wiki_store` 代理导出 `wiki_query`、`wiki_read`、`wiki_save_page` 等工具。
  2. 无论用户在“乳制品行业调研”工作区，还是在“半导体芯片”工作区，甚至在个人私密的策略工作区，智能体都在向同一个全局 `data/wiki/` 读取和沉淀知识。
  3. 这种设计破坏了工作区之间的逻辑隔离，造成不同投资主题之间的词条污染，且无法支持工作区级别的知识打包、备份、归档与清理。
- **用户要求**：
  > “wiki 的保存路径，wiki 应该要保存到工作区内，不应该是所有的工作区共享同一个 wiki。”

---

## 2. 总体设计原则

1. **工作区物理沙箱化（Workspace Sandboxing）**：
   工作区是文件资产与投研知识的**第一法定边界**。一切由任务及其派生子智能体触发的文件搜索、读取、生成、沉淀，严格受限在当前 `workspace_dir` 之内。
2. **零越界保证（Zero Traversal）**：
   无论是 `Glob` 的默认行为，还是模型显式传入带有 `../`、`./` 或绝对路径的参数，工具必须从运行时进行强类型拦截与绝对路径校验，严禁访问任何超出当前工作区根目录的物理路径。
3. **工作区自包含知识体系（Self-Contained Knowledge）**：
   每个工作区内部拥有独立的 `wiki/` 目录，管理专属于该工作区的 `entities/`、`industries/`、`analyses/`、`raw/`、`index.md` 与 `log.md`，实现工作区资产的高度内聚与可迁移性。
4. **平滑演进与历史资产兼容（Smooth Migration & Zero Data Loss）**：
   自动识别历史遗留的全局 `data/wiki/`，将其中的词条平滑迁移至 `default` 默认工作区中，确保既有研报资产不丢失。

---

## 3. 详细设计方案

### 3.1 方案一：工作区沙箱化 `WorkspaceGlob`

#### 3.1.1 架构设计
我们设计并实现 `WorkspaceGlob` 工具，替换主 Agent 与所有 SubAgent 中直接注册的无边界 `Glob` 工具。

```
                    大模型发起 Glob 调用: Glob(pattern="*.md", path="...")
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │       WorkspaceGlob       │
                        └─────────────┬─────────────┘
                                      │
                         path 是否指定目标路径？
                                 /          \
                             是 /            \ 否
                               ▼              ▼
                     计算绝对路径并安全归一化      默认 base_dir = workspace_dir
                     target = (ws / path).resolve()
                               │
                               ▼
              ┌─────────────────────────────────────────────────┐
              │ 越界校验: target.is_relative_to(workspace_dir)？ │
              └────────────────────────┬────────────────────────┘
                               /               \
                           是 /                 \ 否 (越界/逃逸尝试)
                             ▼                   ▼
                  ┌──────────────────────┐   ┌────────────────────────────────┐
                  │ 存在性检查 (is_dir)   │   │ 拦截拒绝:                       │
                  └──────────┬───────────┘   │ Permission Denied: Path escapes│
                             │ 正常          │ current workspace directory.   │
                             ▼               └────────────────────────────────┘
                  ┌──────────────────────┐
                  │ 过滤内部私有目录      │ (自动排除 .tasks/ 等私有沙箱)
                  │ 仅返回工作区文件匹配  │
                  └──────────────────────┘
```

#### 3.1.2 核心实现规则
1. **基准根目录约束**：
   实例化时必须注入当前任务绑定的物理目录 `workspace_dir: Path`。
   若模型未传 `path` 或传 `None` / `""` / `"."`，`base_dir` 强制锚定为 `str(workspace_dir)`。
2. **路径穿越防御（Traversal Defense）**：
   若模型传入了 `path`：
   - 相对路径：使用 `(workspace_dir / path).resolve()` 归一化；
   - 绝对路径：使用 `Path(path).resolve()` 归一化；
   - **硬性断言**：执行 `target_dir.is_relative_to(workspace_dir)`。若结果为 `False`，立即返回：
     ```json
     {"error": "Permission Denied: Path '...' is outside the current workspace. Glob is strictly confined to the current workspace."}
     ```
3. **私有临时目录隐藏**：
   过滤匹配结果，若包含工作区内部私有运行态（如 `.tasks`），默认在返回列表中剔除，保护子智能体的追踪流水与临时大文本截断缓存不被污染展示。
4. **SubAgent 工具链同步赋权**：
   在 `server/agent/subagents/tool_resolver.py` 中，当解析 `file_io` 或 `Glob` 时，由外部传入 `workspace_dir` 动态实例化 `WorkspaceGlob(workspace_dir)`，确保子智能体同样处于工作区沙箱内。

---

### 3.2 方案二：工作区专属 Wiki（Workspace-Isolated Wiki）

#### 3.2.1 物理目录拓扑结构

每个工作区的物理目录升级如下：

```text
workspaces/
├── default/                                   <-- 默认工作区
│   ├── wiki/                                  <-- 工作区专属投研维基知识库
│   │   ├── entities/                          <-- 标的词条 (如 sh600887.md)
│   │   ├── industries/                        <-- 行业逻辑 (如 dairy-industry.md)
│   │   ├── analyses/                          <-- 专题测算底稿
│   │   ├── raw/                               <-- 信源快照
│   │   ├── index.md                           <-- 本工作区维基全量索引地图
│   │   ├── log.md                             <-- 本工作区变更审计日志
│   │   └── SCHEMA.md                          <-- 知识库维护公约规范
│   ├── .tasks/                                <-- 任务私有沙箱
│   └── 伊利股份_投资价值深度分析.md              <-- 共享成果交付物
│
├── ws-semiconductor/                          <-- 半导体专项工作区
│   ├── wiki/                                  <-- 专属半导体知识库，与 default 互不干扰！
│   │   ├── entities/                          <-- 如 sh688981.md (中芯国际)
│   │   ├── industries/                        <-- 如 wafer-foundry.md (晶圆代工)
│   │   └── index.md
│   ├── .tasks/
│   └── 中芯国际与台积电先进制程对比.md
```

#### 3.2.2 动态多租户 WikiStore 工厂与工具绑定

1. **废除硬编码全局 `config.WIKI_DIR` 依赖**：
   - 将 `WikiStore` 彻底解耦为轻量实例，支持传入任意 `root_dir: Path`。
   - `TaskManager` 增加 `get_workspace_wiki_dir(workspace_id: str) -> Path`：
     ```python
     def get_workspace_wiki_dir(self, workspace_id: str) -> Path:
         return self.get_workspace_dir(workspace_id) / "wiki"
     ```
2. **上下文绑定的 Wiki 工具工厂 (`create_wiki_tools`)**：
   在 `server/agent/tools_wiki.py` 中，提供根据 `workspace_dir`（或 `WikiStore` 实例）动态构造绑定工具的工厂函数：
   ```python
   def create_wiki_tools(wiki_root: Path) -> list:
       store = WikiStore(root_dir=wiki_root)
       
       def wiki_query(keyword: str = "", category: str = "") -> str:
           """检索当前工作区投研知识库索引与摘要目录。"""
           return _format_query_result(store.query_wiki(keyword, category))
           
       def wiki_read(rel_path: str) -> str:
           """读取当前工作区特定维基页面完整正文。"""
           return store.read_page(rel_path)
           
       def wiki_save_page(...) -> str:
           """保存分析成果至当前工作区投研知识库。"""
           return store.save_page(...)
           
       def wiki_get_index() -> str:
           """获取当前工作区维基总索引 index.md 内容。"""
           return store.get_index_content()
           
       return [wiki_query, wiki_read, wiki_save_page, wiki_get_index]
   ```
3. **主 Agent 工具挂载**：
   在 `server/agent/core.py:build_agent` 中：
   - 获取当前任务所属工作区的 `wiki_dir = workspace_dir / "wiki"`；
   - 动态调用 `create_wiki_tools(wiki_dir)`，将绑定的 `wiki_query` 和 `wiki_read` 添加至 toolkit。
4. **SubAgent 工具链与委派透传**：
   - 在 `delegate_task` 工具以及 `ToolResolver` 中，透传当前任务所属的 `workspace_dir` 和 `wiki_dir`；
   - 当授权子智能体使用 `wiki_tools` 时，直接提供绑定当前工作区 `wiki` 的工具实例，子智能体写入的维基词条自动沉淀至当前工作区的 `wiki/` 目录下。

#### 3.2.3 系统提示词与 SOP 动态渲染
- **主 Agent 系统提示词**：
  将写死的 `data/wiki/` 调整为动态变量注入：
  - `"你可通过 wiki_query 和 wiki_read 查阅当前工作区本地投研维基（{wiki_dir}）已有成果；"`
  - `"子智能体产出的深度底稿也会自动沉淀在当前工作区的维基中；"`
- **SubAgent 提示词模板**：
  在 `server/agent/subagents/templates.py` 中，`RESEARCH_SPECIALIST_PROMPT` 等模板原本就已支持 `{wiki_dir}` 占位符，由 `tool_resolver` 在实例化时将真实的 `str(workspace_dir / "wiki")` 动态传入，彻底终结模型对 `data/wiki/` 的绝对路径幻觉。

#### 3.2.4 权限引擎（HITL）工作区动态准入
在 `server/agent/core.py` 中：
- `agent._engine.context.working_directories` 注册项从原本的全局 `config.WIKI_DIR` 变更为当前任务工作区的 `str(workspace_dir / "wiki")`。
- 自动免批规则（`PermissionRule`）：
  - 路径白名单动态变更为：`{workspace_dir}/wiki/**` 与 `wiki/**`。

#### 3.2.5 历史维基资产平滑迁移 (Migration)
在 `TaskManager` 初始化或首次加载时：
- 检查历史全局 `data/wiki/` 是否存在有效词条（`entities/`、`industries/`、`analyses/`）；
- 若默认工作区的 `workspaces/default/wiki/` 尚未包含这些文件，将 `data/wiki/` 中的词条、索引及日志安全合并迁移到 `workspaces/default/wiki/` 中；
- 避免重构造成历史沉淀的乳制品等分析成果丢失。

---

## 4. 影响面与变更清单

| 模块 / 文件 | 当前现状 | 改造方案 |
| :--- | :--- | :--- |
| `server/agent/tools_glob.py` (新增) | 无，直接使用 AgentScope 的内置 `Glob` | 新建 `WorkspaceGlob`，继承 `Glob`，强制以 `workspace_dir` 为根并实施越界防护 |
| `server/agent/core.py` | 挂载无边界 `Glob`，写死全局 `data/wiki` 提示与权限 | 替换为 `WorkspaceGlob(workspace_dir)`；动态构造挂载工作区 `wiki_tools`；提示词与 HITL 规则动态化 |
| `server/agent/tools_wiki.py` | 依赖全局单例 `wiki_store` | 增加 `create_wiki_tools(wiki_root)` 工厂函数，返回绑定具体工作区维基的工具集 |
| `server/agent/subagents/tool_resolver.py` | 静态使用全局 `wiki_store` 和无边界 `Glob` | 接收 `workspace_dir`，解析 `Glob` 为 `WorkspaceGlob`，解析 `wiki_tools` 为当前工作区绑定的工具 |
| `server/agent/tools_subagent.py` | `delegate_task` 传递全局 `config.WIKI_DIR` | 传递当前任务的 `workspace_dir / "wiki"` |
| `server/service/task_manager.py` | 仅管理工作区交付物与私有运行态目录 | 增加 `get_workspace_wiki_dir(workspace_id)`，并在启动迁移时合并存量 `data/wiki` 至 `default` 工作区 |
| `tests/test_wiki_store.py` | 测试全局或局部 `WikiStore` | 增加工作区隔离性测试与工具工厂动态调用测试 |
| `tests/test_todo_lifecycle.py` / `tests/test_stock_tools.py` 等 | 现有单测依赖 | 运行全量测试验证，保证零回归 |

---

## 5. 验证与验收准则 (Acceptance Criteria)

1. **Glob 沙箱防逃逸与范围精准性**：
   - 在工作区 A 中调用 `Glob(pattern="*.md")`，仅返回当前工作区根目录及子目录下的文件，不包含任何代码仓库根目录文件、系统文件或其他工作区文件。
   - 显式传入 `path="../../"` 或指向其他工作区的绝对路径，工具必须抛出明确的 `Permission Denied` 拦截信息。
   - 默认排除 `.tasks` 内部私有目录。
2. **Wiki 独立隔离性**：
   - 在工作区 A 创建的维基词条（如 `entities/sh600887.md`），物理保存在 `workspaces/workspace-A/wiki/entities/sh600887.md`，并在工作区 A 的 `wiki/index.md` 中索引。
   - 在工作区 B 中执行 `wiki_query`，无法检索到工作区 A 的私有词条。
   - 子智能体调用 `wiki_save_page` 写入时，精准落盘至父任务所属工作区的 `wiki/` 目录。
3. **自动化测试**：
   - 编写针对 `WorkspaceGlob` 的沙箱约束与逃逸防护测试用例；
   - 编写针对工作区维基多租户隔离与迁移逻辑的单元测试；
   - 全量回归测试 100% 通过。
