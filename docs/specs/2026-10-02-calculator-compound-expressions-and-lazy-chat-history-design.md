# 计算器复合结构支持与极长聊天历史懒加载设计规范

## 1. 背景与问题分析

在复杂多步骤任务（尤其是投研批量股票分析与长篇研究）的实战运行中，暴露了以下两个关键瓶颈问题：

### 问题一：计算器不支持复合数据结构，导致批量运算频发报错
- **报错现场**：
  ```
  【计算失败：Unsupported expression element: Dict(keys=[Constant(value='name'), Constant(value='cost_prot'), ...], values=[...])】
  ```
- **大模型应对困境**：
  大模型在分析股票标的池时，需要计算多个价格分位与风险指标（成本保护线、深度止损位、第一/第二止盈位、技术加仓位等）。大模型自然倾向于使用 Python 字典将分析指标结构化打包：
  `calculate("{'name': '海康威视', 'cost_prot': round(31.025 * 0.9, 2), 'tp1': round(32.46 * 1.15, 2)}")`
  但当前 `server/tools/calculator.py` 中的 `_eval_node` 仅支持单个标量表达式与基础算术运算，缺少对 `ast.Dict` 和 `ast.Set` 的解析，直接抛出 `Unsupported expression element`。
  随后 Agent 不得不妥协退化为“逐个计算”或拆散为纯数组，导致单次分析产生数十次零碎的工具调用，不仅严重拉长响应时间、增加首字延迟，还会引发上下文急速膨胀甚至突破 Token 上限。

### 问题二：长对话历史全量下发与全量渲染导致前端性能劣化
- **性能瓶颈**：
  目前前端切换任务或刷新页面时，通过 `GET /api/tasks/{task_id}/messages` 一次性拉取全部历史。
  当一个任务历经几十轮甚至上百轮深度交互（包含大量长思考过程、子智能体执行轨迹、工具调用卡片、富文本 Markdown 及 Mermaid 图表）时：
  1. 后端一次性序列化数十万 Token 的历史数据，网络传输量可达数兆字节；
  2. 前端 `MessageList.vue` 一次性向 DOM 树灌入数千个复杂节点，引发主线程假死与渲染卡顿；
  3. 缺乏历史分页与懒加载机制，页面滚动掉帧，内存占用居高不下。

---

## 2. 方案权衡与架构决策

### 2.1 计算器改进方案选型

针对用户提出的两个方向：
- **方案 A：原生支持复合结构（Dict、List of Dicts、Set）**
- **方案 B：改为一个一个计算，仅通过 Prompt 强调**

| 评估维度 | 方案 A：支持复合结构 | 方案 B：拆为单值计算 + Prompt 强调 |
|---|---|---|
| **工具调用次数** | **极低（1 次搞定全标的指标）** | 极高（10 只股票需 50~60 次工具调用） |
| **执行延迟与吞吐** | **极快，秒级完成所有计算** | 极慢，多轮往返导致整体响应耗时成倍增加 |
| **Token 消耗** | **省**，大幅减少多轮工具提示与确认帧 | **费**，重复的工具输入输出严重挤占上下文 |
| **鲁棒性与体验** | **高**，彻底消除 AST 报错，直接返回结构化 JSON | **低**，仅靠 Prompt 无法 100% 阻止模型输出字典 |
| **安全性** | **绝对安全**（限定在受控白名单 AST 节点内） | 绝对安全 |

**决策结论**：
**采用「方案 A 为主 + Prompt 引导与格式化优化」的双轨方案**：
1. **底层 AST 引擎增强**：在 `server/tools/calculator.py` 中为 `_eval_node` 增加 `ast.Dict`、`ast.Set` 原生支持；
2. **输出美化呈现**：当求值结果为 `dict` 或包含字典的 `list` 时，自动格式化为美观缩进的 JSON 字符串返回；
3. **Prompt 与工具文档指引**：在主 Agent 系统提示词与 SubAgent 模板中补充说明，明确推荐使用字典打包批量运算，同时给出标准语法示范。

---

### 2.2 聊天历史懒加载方案选型

| 方案 | 原理 | 优缺点分析 | 适用性结论 |
|---|---|---|---|
| **方案 1：纯前端虚拟滚动 (Virtual Scroll)** | 一次性获取全量数据，只渲染可视区域的 10~20 条 DOM | 聊天项高度动态（Markdown、折叠卡片、Mermaid），高度动态预估会导致滚动抖动与展开塌陷，且未解决初始网络传输与后端计算开销 | ❌ 不推荐作为主方案 |
| **方案 2：游标/偏移量分页 + 向上滚动增量加载 (Cursor Pagination with Pull-to-Load-Older)** | 首次仅加载最新 N 条（如最新 30 条）；用户向上滚动触顶或点击时按游标向前增量追加历史 | 行业标准（Slack/ChatGPT/微信同款），首屏加载只需几十毫秒；DOM 节点始终可控；平滑保持滚动锚点（Scroll Anchor） | 🌟 **推荐采纳** |
| **方案 3：全量下发 + 纯前端切片加载 (Client Windowing)** | 后端仍下发全量，前端切片展示 | 未解决后端大报文传输与内存占用问题，治标不治本 | ❌ 不推荐 |

**决策结论**：
采用 **方案 2：基于游标/偏移量的后端分页 + 前端向上滚动/点击增量加载（Scroll Anchor 防抖）**。

---

## 3. 详细设计与实现规范

### 3.1 模块一：计算器复合结构支持（`server/tools/calculator.py`）

#### 3.1.1 AST 解析扩展
在 `_eval_node` 中增加 `ast.Dict` 与 `ast.Set` 的安全求值分支：

```python
def _eval_node(node: ast.AST) -> Any:
    # 1. 常量
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool)):
        return node.value

    # 2. 算术双目与单目运算（原有限定白名单）
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))

    # 3. 列表与元组（已有）
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(elt) for elt in node.elts]

    # 4. 字典复合结构（新增）
    if isinstance(node, ast.Dict):
        return {
            _eval_node(k): _eval_node(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }

    # 5. 集合复合结构（新增）
    if isinstance(node, ast.Set):
        return {_eval_node(elt) for elt in node.elts}

    # 6. 白名单函数调用（已有）
    if isinstance(node, ast.Call):
        ...
```

#### 3.1.2 复合结果返回序列化
当结果为字典或包含字典的对象时，自动使用 `json.dumps(result, ensure_ascii=False, indent=2)` 序列化，返回结构化易读文本，便于大模型快速解析和用户直观查阅。

#### 3.1.3 Prompt 示范强化
在 `server/agent/subagents/templates.py` 与 `server/agent/core.py` 中更新计算器说明：
```markdown
- **结构化批量计算**：当分析多项指标或多只股票时，强烈推荐使用复合字典一次性计算，例如：
  `calculate("{'name': '海康威视', 'cost_prot': round(31.025 * 0.9, 2), 'deep_stop': round(32.46 * 0.85, 2), 'tp1': round(32.46 * 1.15, 2)}")`
```

---

### 3.2 模块二：聊天历史分页与前端懒加载

#### 3.2.1 后端分页接口设计（`GET /api/tasks/{task_id}/messages`）

- **请求参数**：
  - `limit: int = 30`：单次拉取的消息数量（默认 30 条，最大 100 条）；
  - `before_id: str | None = None`：游标，获取该消息 ID 之前的更早历史；不传则默认获取最新的 `limit` 条；
  - `all: bool = False`：可选全量参数，用于特殊备份或导出场景。

- **响应格式**：
  ```json
  {
    "messages": [
      {
        "id": "msg-123",
        "role": "user",
        "text": "分析海康威视...",
        "toolCalls": []
      }
    ],
    "has_more": true,
    "total": 85
  }
  ```

- **分页算法逻辑（`server/service/history.py`）**：
  ```python
  def get_paged_chat_messages(
      state: AgentState | None,
      limit: int = 30,
      before_id: str | None = None,
  ) -> tuple[list[dict[str, Any]], bool, int]:
      all_messages = agent_state_to_chat_messages(state)
      total = len(all_messages)
      if total == 0:
          return [], False, 0

      if before_id:
          # 定位游标索引
          target_idx = next((i for i, m in enumerate(all_messages) if m.get("id") == before_id), -1)
          if target_idx == -1:
              # 游标未找到时回退为首批
              end_idx = total
          else:
              end_idx = target_idx
      else:
          # 首次加载：取最后 limit 条
          end_idx = total

      start_idx = max(0, end_idx - limit)
      paged = all_messages[start_idx:end_idx]
      has_more = start_idx > 0
      return paged, has_more, total
  ```

#### 3.2.2 前端 Session Store 状态扩展（`frontend/src/store/session.ts`）

在 `SessionData` 中增加分页元数据：
```ts
interface SessionData {
  messages: ChatMessage[]
  hasMoreHistory: boolean
  isLoadingMoreHistory: boolean
  totalHistoryCount: number
  ...
}
```

- **初始加载 `loadHistory(taskId)`**：
  - 调用 `/api/tasks/${taskId}/messages?limit=30`；
  - 赋值 `s.messages = res.messages`；
  - 记录 `s.hasMoreHistory = res.has_more`，`s.totalHistoryCount = res.total`。
- **加载更多 `loadMoreHistory(taskId)`**：
  - 若 `!s.hasMoreHistory || s.isLoadingMoreHistory`，直接返回；
  - 取当前最早一条消息的 ID：`const firstId = s.messages[0]?.id`；
  - 调用 `/api/tasks/${taskId}/messages?limit=30&before_id=${firstId}`；
  - **前置追加（Prepend）**：`s.messages = [...res.messages, ...s.messages]`；
  - 更新 `s.hasMoreHistory = res.has_more`。

#### 3.2.3 交互与滚动位置保持（Scroll Anchor）

在 `MessageList.vue` 或 `SidebarMiddle.vue` 中：
1. **顶部操作条**：
   在消息列表顶端增加加载控制条：
   ```html
   <div v-if="session.hasMoreHistory" class="history-loader">
     <button
       class="load-more-btn"
       :disabled="session.isLoadingMoreHistory"
       @click="loadEarlierMessages"
     >
       <span v-if="session.isLoadingMoreHistory" class="spinner" />
       <span>{{ session.isLoadingMoreHistory ? '正在加载更早历史...' : `查看更早的消息 (还有 ${session.remainingHistoryCount} 条)` }}</span>
     </button>
   </div>
   ```
2. **滚动触顶自动加载与位置锚定（Zero Scroll Jitter）**：
   ```ts
   async function loadEarlierMessages() {
     const container = scrollContainerRef.value
     if (!container) return

     // 记录加载前的滚动高度与滚动条位置
     const previousScrollHeight = container.scrollHeight
     const previousScrollTop = container.scrollTop

     await session.loadMoreHistory(props.taskId)

     // 消息前置渲染后，通过高度差恢复精确视口，用户视觉毫无跳动
     await nextTick()
     const heightDifference = container.scrollHeight - previousScrollHeight
     container.scrollTop = previousScrollTop + heightDifference
   }
   ```
3. **实时流式无缝衔接**：
   当用户处于对话底部且有新的流式 chunk 时，`McLayoutContent` 既有的 `autoScroll=true` 依然生效；历史消息只在顶部增量插入，与底部的实时流完全正交。

---

## 4. 接口与代码变更影响清单

| 模块 / 文件 | 变更说明 |
|---|---|
| `server/tools/calculator.py` | 增强 `_eval_node`，增加对 `ast.Dict`、`ast.Set` 的安全解析，完善 JSON 格式化输出 |
| `server/service/history.py` | 增加 `get_paged_chat_messages` 分页函数，支持 `limit` 与 `before_id` 游标 |
| `server/main.py` | 更新 `GET /api/tasks/{task_id}/messages` 接收 `limit` 与 `before_id` 参数 |
| `server/agent/core.py` & `templates.py` | 更新计算器工具描述与 Prompt 示例，展示字典批量指标计算 |
| `frontend/src/store/session.ts` | 增加 `hasMoreHistory`、`loadMoreHistory`，支持游标分页前置增量合并 |
| `frontend/src/components/chat/MessageList.vue` | 顶部增加更早历史加载按钮、加载中指示器及滚动触顶侦测 |
| `tests/test_calculator.py` | 增加字典与嵌套复合结构的单元测试（Dict, List of Dict, round 嵌套） |
| `tests/test_chat_stream.py` / 新增单测 | 增加消息游标分页测试，验证 `limit`、`before_id` 与边界情况 |
| `frontend/tests/store/session.spec.ts` | 增加前端消息增量分页与前置合并测试 |

---

## 5. 验证与测试计划

1. **计算器单测验证**：
   - 字典计算：`{'name': '海康威视', 'cost_prot': round(31.025 * 0.9, 2)}` 成功解析并返回 JSON 键值对；
   - 嵌套字典与列表：`[{'stock': '平安银行', 'pnl': pnl(100, 10.0, 12.0)}]` 成功解析；
   - 非法语法与未知函数拦截：验证安全性不变。
2. **长历史分页验证**：
   - 50 条消息场景下，首次加载返回最新的 30 条，`has_more = True`；
   - 传入最旧一条消息的 `before_id`，正确返回剩余的 20 条，`has_more = False`；
   - 前端触发加载更早历史，页面消息总数变为 50，且滚动条保持当前内容位置不闪烁。
3. **全栈回归与构建测试**：
   - 后端 pytest 全量通过；
   - 前端 vitest 全量通过；
   - 前端打包构建 `npm run build` 成功。
