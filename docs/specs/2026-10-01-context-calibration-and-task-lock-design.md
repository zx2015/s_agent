# Token 窗口自动校准与任务并发互斥锁设计规范

> 状态：PROPOSED / IN_PROGRESS  
> 日期：2026-10-01  
> 模块：`server/agent/calibrator.py`, `server/agent/core.py`, `server/service/task_manager.py`, `server/main.py`, `frontend/src/composables/useChat.ts`

---

## 一、背景与动机

在 s_agent 从通用任务助手向金融股票分析智能体演进的过程中，针对 Agent 运行时与 API 层的深度审查发现了两个关键短板：

1. **Token 上下文窗口校准滞后**：
   - AgentScope 的对话上下文自动压缩机制依赖：
     $$\text{当前 Token 消耗} \ge \text{context\_size} \times \text{trigger\_ratio}$$
   - 目前 `OpenAIChatModel` 使用了写死的配置 `context_size = config.MODEL_CONTEXT_SIZE`（默认 128,000）。当本地 LiteLLM 路由至真实窗口仅为 32,768 的轻量模型（如 `v-flash` / `qwen3.8-flash`）时，自动压缩触发时机偏晚，极易在达到压缩阈值前触发上游 API 的 `context_length_exceeded` 异常；
   - 当替换为 1M 窗口的超长上下文模型（如 Gemini 2.5 Flash / DeepSeek V4）时，写死 128k 又会导致过早丢弃早期历史，无法利用模型的长文本能力。因此需要**替换模型后免配置的自适应自动校准机制**。

2. **同一 `task_id` 并发请求状态撕裂**：
   - 当用户在前端快速连击“发送”按钮、网络断线重试、或多个前端客户端/自动化脚本对同一个 `task_id` 同时调用 `POST /api/chat` 时；
   - 后端针对同一个任务存在多个并发执行的 `agent.reply_stream()` 协程；
   - 这些协程并发写入同一个 `agent.state.context`、操作同一个工作区目录（并发调用 `Write`/`Edit`/`Bash`），导致状态污染、文件写入竞态撕裂以及 SSE 乱序推送；
   - 需要建立针对单个任务的**细粒度并发互斥锁（Mutex Lock）与 409 快速失败/排队保护机制**。

---

## 二、Token 窗口自动校准架构设计

### 2.1 四级自适应嗅探流水线

为了在用户替换任何模型（包括各类开源模型、商业模型、自定义别名路由）后无需手动重新计算与修改配置，设计如下四级解析流水线：

```
       ┌────────────────────────────────────────────────────────┐
       │ 1. 显式环境变量覆盖 (Highest Priority)                   │
       │    若 S_AGENT_MODEL_CONTEXT_SIZE 为正整数，直接使用该数值    │
       └──────────────────────────┬─────────────────────────────┘
                                  │ 为 "auto" 或 未指定
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │ 2. 运行时主动嗅探 (Active Probe)                         │
       │    向上游 LiteLLM /model/info 与 /models 发起探测          │
       │    提取 max_input_tokens 或 target model max_tokens    │
       └──────────────────────────┬─────────────────────────────┘
                                  │ 网络不可达 / 未暴露元数据
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │ 3. 知名模型家族正则匹配规则库 (Heuristic Fallback)         │
       │    根据模型名 pattern 推导标准窗口 (gemini, deepseek,   │
       │    claude, gpt-4o, qwen-flash 等)                       │
       └──────────────────────────┬─────────────────────────────┘
                                  │ 无法匹配任何模式
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │ 4. 保守安全兜底值 (Safe Default, 128,000 / 32,768)       │
       └────────────────────────────────────────────────────────┘
```

### 2.2 内存缓存与性能保护
- 每次服务生命周期内，针对同一个 `model_name` 的解析结果在 `_context_size_cache` 字典中持久缓存；
- 探测过程设置严格的超时时间（2.0s），若上游端点未就绪或报错，静默降级至规则匹配，绝不阻塞 Agent 构建与启动。

### 2.3 知名模型正则映射表
- `gemini[-/].*flash|gemini[-/].*pro` $\to$ 1,048,576
- `deepseek[-/].*v4|deepseek[-/].*pro` $\to$ 1,000,000
- `claude[-/]3[-.]5|claude[-/]3[-.]7` $\to$ 200,000
- `gpt-4o|o1|o3` $\to$ 128,000
- `qwen.*3\.8[-_]flash|qwen.*flash[-_]next` $\to$ 32,768
- `qwen.*3[-.]5|qwen[-/]qwen` $\to$ 131,072
- `minimax[-/]m3` $\to$ 1,000,000

---

## 三、同一 `task_id` 并发互斥锁设计

### 3.1 任务互斥锁生命周期
- 在 `TaskManager` 中维护内存锁表：`self._task_locks: dict[str, asyncio.Lock] = {}`；
- 提供安全的获取方法：`get_task_lock(self, task_id: str) -> asyncio.Lock`；
- 当任务被归档或彻底删除时，一并清理对应锁对象。

### 3.2 快速失败（HTTP 409 Conflict）拦截机制
在 `server/main.py` 的 `POST /api/chat` 处理链路中：
1. **握手前防重检查**：
   在开始流式输出前，先检测 `lock.locked()`：
   - 若当前任务已有正在执行的对话流，立即抛出 `HTTP 409 Conflict`：
     ```json
     {"detail": "Task <task_id> is currently busy processing another message."}
     ```
   - 避免无效挂起 HTTP 连接，防止客户端连击导致的连接堆积与无序排队；
2. **流式期间独占持有**：
   在 `event_stream()` 异步生成器内部使用 `async with lock:` 包裹核心处理循环：
   - 保证直到最后一个 `done` 帧产生且状态保存完成（或网络异常中断触发 `finally`）后，才释放该锁；
3. **前端防重与友好提示**：
   前端 `useChat.ts` 捕获到状态码为 `409` 的 `ApiError` 时，向对话流输出友好的提示信息：
   `[任务正在处理上一条消息，请稍后再试]`，并重置流式状态，避免转圈假死。

---

## 四、接口与配置契约

### 4.1 环境变量规范 (`server/config.py`)
- `S_AGENT_MODEL_CONTEXT_SIZE`：
  - 设为 `"auto"`（默认）：启用自适应自动校准；
  - 设为具体正整数（如 `"32768"` 或 `"1048576"`）：固定强制使用该 Token 数，跳过探测。

### 4.2 错误状态码契约
| 端点 | 状态码 | 含义 |
|---|---|---|
| `POST /api/chat` | `404 Not Found` | 任务不存在 |
| `POST /api/chat` | `409 Conflict` | 该任务当前正忙（另一个消息流正在处理中） |
| `POST /api/chat` | `200 OK (text/event-stream)` | 成功建立 SSE 流式连接 |

---

## 五、测试验证规划

1. **自动校准测试 (`tests/test_calibrator.py`)**：
   - 测试通过 mock `/model/info` 端点返回 32768，成功解析并缓存；
   - 测试通过 mock `/models` 端点返回 1048576，成功解析并缓存；
   - 测试无上游网络时，基于模型名称正则准确匹配；
   - 测试未知模型时回退到默认兜底值；
   - 测试环境变量显式覆盖生效；
2. **并发互斥锁测试 (`tests/test_task_concurrency.py`)**：
   - 单任务顺序调用成功执行；
   - 单任务并发两次调用时，第二个请求立即抛出 HTTP 409；
   - 第一个请求执行完毕后，后续请求可正常获取锁并执行；
   - 不同任务（Task A 与 Task B）并发执行互不影响；
3. **前端兼容性验证**：
   - 运行前端现有 vitest 测试集，确保 100% 通过。
