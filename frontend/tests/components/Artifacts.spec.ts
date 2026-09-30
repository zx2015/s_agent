import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DiffPane from '@/components/artifacts/DiffPane.vue'
import ArtifactTabs from '@/components/artifacts/ArtifactTabs.vue'
import DownloadPane from '@/components/artifacts/DownloadPane.vue'
import { useSessionStore } from '@/store/session'

describe('ArtifactTabs', () => {
  it('renders all five tabs', () => {
    const wrapper = mount(ArtifactTabs, {
      props: { activeTab: 'preview' },
    })
    expect(wrapper.text()).toContain('产物预览')
    expect(wrapper.text()).toContain('待办')
    expect(wrapper.text()).toContain('全部文件')
    expect(wrapper.text()).toContain('文件变更')
    expect(wrapper.text()).toContain('下载')
  })

  it('marks the active tab', () => {
    const wrapper = mount(ArtifactTabs, {
      props: { activeTab: 'diff' },
    })
    const active = wrapper.findAll('.tab.active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('文件变更')
  })

  it('emits update on tab click', async () => {
    const wrapper = mount(ArtifactTabs, {
      props: { activeTab: 'preview' },
    })
    const tabs = wrapper.findAll('.tab')
    // After adding 'todos', the indices are preview(0), todos(1), files(2),
    // diff(3), download(4).
    await tabs[3].trigger('click')
    expect(wrapper.emitted('update:activeTab')?.[0]).toEqual(['diff'])
  })
})

describe('DiffPane', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches and renders the diff for the task', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ diff: '-old\n+new' }),
      }),
    )
    const wrapper = mount(DiffPane, { props: { taskId: 't1' } })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('-old')
    })
  })

  it('shows empty message when there is no diff', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ diff: '' }),
      }),
    )
    const wrapper = mount(DiffPane, { props: { taskId: 't1' } })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('工作区没有未提交的变更')
    })
  })

  it('counts added and removed lines in the summary', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ diff: '--- a\n+++ b\n+x\n-y\n-z' }),
      }),
    )
    const wrapper = mount(DiffPane, { props: { taskId: 't1' } })
    await vi.waitFor(() => {
      expect(wrapper.find('.diff-hint').text()).toBe('+1 / -2')
    })
  })
})

describe('DownloadPane', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('lists artifacts from the session store', () => {
    const session = useSessionStore()
    session.applyFrame({
      event: 'artifact_created',
      data: { type: 'html', file_path: 'index.html', url: '/api/x' },
    } as never)

    const wrapper = mount(DownloadPane, { props: { taskId: 't1' } })
    expect(wrapper.text()).toContain('index.html')
  })

  it('shows empty state with no artifacts', () => {
    const wrapper = mount(DownloadPane, { props: { taskId: 't1' } })
    expect(wrapper.text()).toContain('暂无产物')
  })
})
