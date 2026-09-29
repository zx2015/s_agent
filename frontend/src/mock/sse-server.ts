/**
 * A local SSE simulator so the workbench can be built without the backend.
 *
 * Every frame this module emits is a real frame — the tests run them
 * through the production parser. That constraint is the point: a mock that
 * invents its own shapes would let the UI be built against a contract the
 * backend does not speak, and the gap would only surface at integration.
 *
 * It is deliberately keyword-driven so the common demo paths — a shell
 * command, a page generation, a destructive command — are all reachable
 * from the UI without a live model.
 */

const THINKING = '正在理解你的请求…'
const CHUNK_DELAY_MS = 60
const CHAR_DELAY_MS = 12

function frame(event: string, payload: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Produce a simulated agent turn for a user message.
 *
 * @param message - The user's message, used to pick which events to emit.
 * @param pause - Delay helper, injectable so tests run without real waits.
 * @yields Raw SSE frames, in the same encoding the backend produces.
 */
export async function* mockTurn(
  message: string,
  pause: (ms: number) => Promise<void> = sleep,
): AsyncGenerator<string> {
  const isDangerous = /删除|rm -rf|清空/.test(message)
  const isShell = /执行|shell|命令|ls|npm/.test(message)
  const isPage = /网页|页面|html|原型/.test(message)

  yield frame('thinking_delta', { text: THINKING })
  await pause(CHUNK_DELAY_MS)

  // A destructive request pauses for human approval before doing anything.
  if (isDangerous) {
    yield frame('require_confirm', {
      reply_id: 'r-mock-1',
      command: 'rm -rf build',
      reason: '该命令会删除目录，属于高危操作',
      action: 'allow',
    })
    await pause(CHUNK_DELAY_MS)
  }

  if (isShell) {
    yield frame('tool_call_start', {
      call_id: 'c-mock-1',
      tool: 'shell',
      args: { command: 'ls -la' },
    })
    await pause(CHUNK_DELAY_MS)
    yield frame('tool_call_end', {
      call_id: 'c-mock-1',
      status: 'success',
      result_summary: 'total 12\ndrwxr-xr-x  src\n-rw-r--r--  package.json',
    })
    await pause(CHUNK_DELAY_MS)
  }

  const reply = `收到你的请求：${message}。这是模拟回复，用于在未接入后端时调试界面。`
  for (const char of reply) {
    yield frame('text_delta', { text: char })
    await pause(CHAR_DELAY_MS)
  }

  if (isPage) {
    yield frame('artifact_created', {
      type: 'html',
      file_path: 'index.html',
      url: '/mock/artifacts/index.html',
    })
    await pause(CHUNK_DELAY_MS)
  }

  yield frame('done', { task_status: 'completed' })
}