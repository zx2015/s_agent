# 会话（Conversation）与记忆管理设计

> **文档版本**：v1.0
> **创建日期**：2026-09-30
> **状态**：已实现并实测验证（非纯设计稿）
> **文档位置**：`docs/specs/2026-09-30-conversation-memory-management.md`
> **关联**：本文档是 [2026-09-28-stage1-single-agent-design.md](2026-09-28-stage1-single-agent-design.md) 「模块 D：记忆管理」的**实际落地版本**——该文档写于实现之前，对 AgentScope API 的假设（`MemoryBase`/`ToolOffloadMiddleware`/`AgenticMemoryMiddleware`/`CompressionConfig` 等）与实际安装的 2.0.8 源码不符，请以本文档为准。

---

## 一、设计目标与总体结论

用户需求："conversation history 能长久化"，并且要求"各个任务/conversation 间的 context 互相隔离"。当前实现同时满足两点，且**均已用真实实验验证，不是纯理论推导**：

| 需求 | 结论 | 验证方式 |
|---|---|---|
| 跨后端进程重启保留对话历史 | ✅ 已实现（Redis 持久化） | 让模型记住一个数字 → `kill -9` 强杀后端进程 → 全新进程正确答出该数字 |
| 不同任务间上下文完全隔离 | ✅ 已实现（架构级隔离，非偶然） | 两个任务各自被告知不同暗号 → 交叉询问，无串号 |

---

## 二、隔离模型：一个 Task 就是一个 Conversation

### 2.1 基本单位

前端每个"任务"（`task_id`）对应后端**唯一一个** AgentScope `Agent` 实例。不存在"多个 conversation 共享一个 Agent"或"一个 conversation 跨多个 Agent"的情况——task 和 conversation 是同一个东西的两个名字。

### 2.2 隔离的四个层次

```
task_id
  ├─ 内存层：TaskManager._agents[task_id] -> 独立的 Agent 实例
  │            （独立 Toolkit、独立 LocalBackend、独立 Model/Credential 对象、独立 AgentState）
  ├─ 持久化层：Redis key `s_agent:agent_state:{task_id}` -> 独立存储
  ├─ 文件层：workspaces/{task_id}/ -> 独立工作区目录
  └─ 版本控制层：workspaces/{task_id}/.git -> 独立 git 仓库
```

关键代码（`server/service/task_manager.py`）：

```python
class TaskManager:
    self._agents: dict[str, Agent] = {}   # key 即 task_id，天然不会串

async def get_or_create_agent(self, task_id: str) -> Agent:
    if task_id not in self._agents:
        saved_state = await agent_state_store.load(task_id)   # 按 task_id 精确加载
        self._agents[task_id] = await build_agent(
            self.workspace_dir(task_id),                       # 按 task_id 分配独立目录
            state=saved_state,
        )
    return self._agents[task_id]
```

`build_agent()`（`server/agent/core.py`）每次调用都**从零构建**一套完全独立的环境——全新 `Toolkit()`、绑定该任务专属目录的 `LocalBackend`、全新的 `OpenAIChatModel`/`OpenAICredential` 对象——没有任何跨任务共享的可变状态。这意味着隔离性是架构上"切死"的，不是靠约定或运气。

### 2.3 已知边界情况（非 bug，但需要知道）

隔离的粒度是 **task**，不是"某次 HTTP 请求"或"某个浏览器标签页"。如果两个标签页同时打开**同一个** task 并各自发消息，它们会共享同一份历史（这是预期行为——同一个任务本来就该是同一段对话）。

⚠️ **尚未处理的并发风险**：当前代码没有对同一个 `task_id` 做互斥锁。如果同一个 task 被两个请求几乎同时调用 `/api/chat`，两个协程会同时操作同一个 `Agent`/`AgentState` 对象，可能导致对话状态交叉写坏。这个场景本次未做修复，记录在案（见「六、尚未实现的部分」）。

---

## 三、内存态：进程存活期间的对话历史

每个 `Agent` 内部有一个 `agentscope.state.AgentState`（纯 pydantic `BaseModel`），其 `context` 字段就是该任务完整的消息序列（用户消息、助手回复、工具调用、工具结果，按顺序追加）。只要后端进程不重启，`TaskManager._agents` 这个内存字典就一直持有它，无需任何额外操作即可支持多轮对话。

### 3.1 AgentScope 内置的记忆机制（未定制，但已生效）

我们完全没有传自定义的 `ContextConfig`/`InjectionConfig`，走的是 AgentScope 的默认值——但默认值本身就已经实现了原规划文档「模块 D」四大机制里的两项：

**上下文注入**（对应原规划 D-1）：`InjectionConfig.inject_runtime_state` 默认 `True`。每轮回复开始时，框架会往对话上下文追加一条 `<system-reminder>` 消息（当前时间、待办任务状态、上下文长度预警），作为独立消息插入，不写进 system prompt 字符串本体（这样系统提示词本身可以被模型服务商做 prompt caching）。详见 `CLAUDE.md`「System Prompt 的实际组装方式」一节。

**自动压缩**（对应原规划 D-3）：`ContextConfig` 默认 `trigger_ratio=0.8`、`reserve_ratio=0.1`。当估算 token 数达到 `0.8 × model.context_size` 时，框架自动把较早的历史消息喂给模型生成结构化摘要（`compression_prompt`/`summary_template`），存入 `state.summary`，只保留最近 10% 的原始对话不压缩。

⚠️ **已知校准缺口**：`OpenAIChatModel` 的 `context_size` 用的是 AgentScope 默认值 **128000**，未针对 `v-flash` 实际的上下文窗口做校正——如果真实上限比这个小，压缩触发得会偏晚（见 TODO.md）。

---

## 四、跨进程重启持久化：Redis + AgentState

### 4.1 为什么持久化单元是 `AgentState`

`AgentState`（`agentscope.state.AgentState`）是纯 pydantic `BaseModel`，覆盖 `context`（完整消息历史）、`summary`（压缩摘要）、以及工具/任务/权限子上下文。它天然支持 `model_dump_json()` / `model_validate_json()` 序列化，而且 `Agent(state=...)` 构造参数**直接接受**这个对象来恢复——不需要自己拼消息列表、不需要理解内部结构。

这不是本项目发明的取巧做法：AgentScope 自己的高阶存储后端（`agentscope.app.storage.RedisStorage`/`SQLStorage`，用于其官方 `create_app()` 服务层）内部持久化的正是同一个 `AgentState` 对象（`from ...state import AgentState`）。

> ⚠️ **官方在线文档的误导**：`doc.agentscope.io` 的 State/Session Management 页面描述的是 `StateModule` / `agent.state_dict()` / `agent.load_state_dict()` / `agentscope.session.JSONSession` 这套 API，但本地实际安装的 2.0.8 源码（`/media/data/git/agentscope/src/agentscope`，editable 模式）里 `agentscope.session` 模块根本不存在（`import agentscope.session` 直接 `ModuleNotFoundError`），`Agent` 也没有 `state_dict()` 方法。**遇到类似情况以本地实际安装的源码为准，不要盲信在线文档**——这与本项目从 AgentScope 1.0.21 升级到 2.0 时踩过的 API 不一致坑是同一类问题。

### 4.2 为什么选 Redis 而不是 JSON 文件

本机已有一个专门为此预留的 Redis 容器（宿主机端口 6380），相比 `workspaces/registry.json` 那种手写 JSON 文件方案：
- 原子写入，不用自己实现"写临时文件再 rename"防止写一半崩溃导致文件损坏
- 天然支持 TTL，被遗弃的任务历史能自动过期清理，不用另写清理任务
- 面向未来：如果以后要跑多个后端 worker 进程，Redis 天然支持并发访问，而文件方案需要额外加文件锁

### 4.3 保存时机：只在整轮真正结束时

`server/main.py` 的 `/api/chat` 处理逻辑里，只在收到 `ReplyEndEvent`（一整轮回复完全结束，包括期间可能发生的 HITL 确认往返）时才调用 `task_manager.save_agent_state(task_id)`，**不在工具调用等待用户确认期间保存**。

原因：如果在工具调用还没得到确认结果时就保存快照，恢复出来的状态会包含"发出了工具调用但没有对应结果"的不一致结构——AgentScope 的 `reply_stream()` 对这种状态会直接抛错（`"Agent is waiting for N tool calls ... but received no event"`，这是我们在早期联调时真实踩到过的报错）。只在完整轮次结束后保存，能保证恢复出来的状态永远是自洽的；代价是如果进程恰好在一次"等待用户点确认"的过程中崩溃，这一轮未完成的对话会丢失（但不会产生损坏状态）。

### 4.4 保存失败与加载失败：非对称的容错策略

```python
async def save_agent_state(self, task_id: str) -> None:
    agent = self._agents.get(task_id)
    if agent is None:
        return
    try:
        await agent_state_store.save(task_id, agent.state)
    except Exception:
        logger.warning(...)   # 记日志，不抛出
```

**保存失败只记日志、不抛出**：因为调用这个方法时，该轮回复的所有 SSE 帧（包括翻译器为 `ReplyEndEvent` 生成的 `done` 帧）早就已经发给前端了。如果这里抛异常，会被 `main.py` 外层的 `except Exception` 捕获，导致又给前端补发一次多余的 `done`/错误帧，污染一个本来已经成功的回复。

**加载失败则保持原样往外抛**（`get_or_create_agent` 里的 `agent_state_store.load(...)` 调用没有额外包 try/except），交给 `/api/chat` 已有的"缺 API key"式优雅降级处理——因为对话刚开始时如果历史读取失败，用户应该看到明确的报错，而不是被悄悄当成"这个任务本来就没有历史"，那样会掩盖一个真实的数据问题。

`AgentStateStore.load()` 内部还对**反序列化失败**（比如以后升级 AgentScope 导致 `AgentState` 的 pydantic schema 变了，旧数据校验不过）做了单独处理：捕获 `ValidationError`，记警告日志后返回 `None`，等效于"当作没有历史"处理，而不是让整个请求 500——这与前面"加载失败要往外抛"并不矛盾，因为这里的失败原因很明确（数据格式不兼容），选择继续、而不是让一次版本升级导致所有旧任务都无法使用是更合理的取舍。

### 4.5 Key 方案与 TTL

```
s_agent:agent_state:{task_id}
```

TTL 默认 30 天（`S_AGENT_STATE_TTL_DAYS` 环境变量可调），每次保存都会刷新过期时间——只要任务还在被使用就不会过期，真正被遗弃的任务会在 30 天不活动后自动从 Redis 里消失（工作区文件和任务元数据不受影响，只是对话历史没了）。

---

## 五、Redis 本身的持久化特性（运维层面，非应用代码）

这一层跟前面的应用设计是分开的问题：**即使应用代码把 `AgentState` 正确写进了 Redis，Redis 自己会不会把这份数据保住，取决于 Redis 自身的持久化配置。**

### 5.1 当前配置（`/media/data/redis/docker-compose.yaml`）

```yaml
image: redis:latest
restart: always
volumes:
  - /media/data/redis/volumns:/data
```

实测确认：
- **RDB 快照开启**，策略 `save 3600 1 300 100 60 10000`（默认值，未定制）
- **AOF（Append Only File）关闭**（`appendonly no`）
- 数据目录是宿主机 bind mount，容器本身被删除重建不影响数据

### 5.2 两种"重启"，结果完全不同——已用真实实验验证

| 场景 | 结果 | 原因 |
|---|---|---|
| 优雅重启（`docker restart`，或本机 `crontab` 里每晚 3 点的 `/usr/sbin/reboot`） | ✅ 数据保留 | 收到 `SIGTERM` 时 Redis 会在退出前主动做一次保存；`reboot` 走的是 systemd 正常关机流程，会给 docker 服务优雅停止的机会 |
| 暴力终止（`docker stop -s SIGKILL`，模拟断电/OOM killer） | ❌ 数据丢失（丢的是上次快照之后的写入） | 没有 AOF，RDB 快照默认策略下"改动 ≥1 个 key 且过去 1 小时"才存一次；暴力终止时来不及触发这次保存 |

本机 crontab 确认存在 `00 03 * * * /usr/sbin/reboot`（每晚定时重启），已验证这个特定场景是安全的（用 `systemctl stop docker` → `systemctl start docker` 模拟了同样的优雅关闭/自动拉起流程，数据完好，容器因 `restart: always` 策略自动恢复）。

### 5.3 剩余风险与待办

真正意外的断电/内核 panic/OOM 强杀仍然可能丢失"最近一次快照之后"的写入（对我们这种低频写入场景，最坏情况下窗口接近 1 小时）。**已决定暂不处理**（用户明确表示"先这样吧，先用 Redis 存"），但如果以后要收紧这个风险，做法是给 Redis 开启 AOF（`appendonly yes`，`appendfsync everysec` 最多丢 1 秒数据）——需要注意这个 Redis 实例是本机共用基础设施，改动前要确认有没有其它项目也在用它。

---

## 六、尚未实现的部分

对照原规划文档「模块 D：记忆管理」的四大机制，如实标注现状：

| 机制 | 状态 | 说明 |
|---|---|---|
| 上下文注入 | ✅ 已生效 | AgentScope 默认行为，见「三、3.1」 |
| 压缩 | ✅ 已生效 | AgentScope 默认行为，`context_size` 未校准（见「三」末尾） |
| 跨进程重启持久化 | ✅ 已实现 | 本文档主体内容 |
| 卸载（Context Offload） | ❌ 未实现 | AgentScope 提供 `Offloader`/`WorkspaceBase` 接口，`Agent(offloader=...)` 当前传的是 `None`（默认值） |
| 长期记忆（跨任务知识库） | ❌ 未实现 | AgentScope 有 `agentscope.rag` 模块可接入检索增强知识库，当前未创建/挂载任何知识库 |
| 同一 task 并发请求加锁 | ❌ 未实现 | 见「二、2.3」的已知边界情况 |

---

## 七、相关代码索引

| 关注点 | 文件 |
|---|---|
| 每任务 Agent 装配、System Prompt 组装 | `server/agent/core.py` |
| 任务/工作区注册表、Agent 缓存、HITL 确认桥接、保存时机调度 | `server/service/task_manager.py` |
| Redis 持久化实现（`AgentStateStore`） | `server/service/memory_store.py` |
| SSE 事件翻译、`/api/chat` 主循环 | `server/main.py`、`server/service/events.py` |
| Redis/TTL 环境变量 | `server/config.py`、`.env.example` |
| 单元与集成测试 | `tests/test_memory_store.py`（真实连接本地 Redis）、`tests/test_task_manager.py` |

## 八、参考资料

- [2026-09-28-stage1-single-agent-design.md](2026-09-28-stage1-single-agent-design.md) — 原始规划（模块 D 的 API 假设已被本文档修正）
- [../../CLAUDE.md](../../CLAUDE.md) —「System Prompt 的实际组装方式」「会话历史持久化」两节
- [../../TODO.md](../../TODO.md) — 记忆机制相关待办项
