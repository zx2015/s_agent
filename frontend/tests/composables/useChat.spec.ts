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

  it('requires an active task', async () => {
    const session = useSessionStore()
    const { send } = useChat()
    await send('你好')
    // Without a task there is nowhere to run, so only the user message
    // is recorded and no turn is opened.
    expect(session.messages).toHaveLength(1)
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