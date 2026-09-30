import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '@/store/session'
import { useWorkspaceStore } from '@/store/workspaces'
import { useChat } from '@/composables/useChat'

function seedTask() {
  const workspace = useWorkspaceStore()
  workspace.setWorkspaces([
    {
      id: 'w1',
      name: 'W',
      tasks: [
        {
          id: 't1',
          title: 'T',
          workspaceId: 'w1',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        },
      ],
    },
  ])
  workspace.selectTask('t1')
}

describe('useChat', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('appends the user message and opens an assistant turn', async () => {
    // An active task is required to run; the stream itself is stubbed so the
    // test does not depend on a backend.
    seedTask()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => '' }),
    )

    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')
    expect(session.messages[0].role).toBe('user')
    expect(session.messages[1].role).toBe('assistant')
  })

  it('auto-creates and selects a task when none is active', async () => {
    // Sending with no active task used to only echo the user's bubble and
    // stop — this proves it now creates a task via the backend first.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'auto-1',
          title: '新任务',
          workspaceId: 'default',
          status: 'running',
          updatedAt: '',
          hasArtifacts: false,
        }),
      }),
    )

    const workspace = useWorkspaceStore()
    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')

    expect(workspace.activeTaskId).toBe('auto-1')
    expect(session.messages[0].role).toBe('user')
    expect(session.messages[1].role).toBe('assistant')
  })

  it('reports an error in the transcript when task auto-creation fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))

    const workspace = useWorkspaceStore()
    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')

    expect(workspace.activeTaskId).toBeNull()
    expect(session.messages[1].text).toContain('无法创建任务')
    expect(session.isStreaming).toBe(false)
  })

  it('does not send while a turn is already streaming', async () => {
    seedTask()

    const session = useSessionStore()
    session.beginAssistantTurn()

    const { send } = useChat()
    await send('第二条')
    expect(session.messages).toHaveLength(1)
  })

  it('stop marks the current turn finished', async () => {
    const session = useSessionStore()
    session.beginAssistantTurn()
    const { stop } = useChat()
    stop()
    expect(session.isStreaming).toBe(false)
  })
})