import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DiffPane from '@/components/artifacts/DiffPane.vue'
import ArtifactTabs from '@/components/artifacts/ArtifactTabs.vue'
import DownloadPane from '@/components/artifacts/DownloadPane.vue'
import PreviewPane from '@/components/artifacts/PreviewPane.vue'
import StandaloneArtifactViewer from '@/components/artifacts/StandaloneArtifactViewer.vue'
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

describe('PreviewPane', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders empty message when artifact is null', () => {
    const wrapper = mount(PreviewPane, { props: { artifact: null } })
    expect(wrapper.text()).toContain('选择左侧产物以预览')
  })

  it('renders iframe when artifact is HTML', () => {
    const wrapper = mount(PreviewPane, {
      props: {
        artifact: {
          type: 'html',
          filePath: 'index.html',
          url: '/api/tasks/t1/artifacts/preview/index.html',
        },
      },
    })
    expect(wrapper.find('iframe.preview-frame').exists()).toBe(true)
    expect(wrapper.text()).toContain('index.html')
  })

  it('renders markdown with McMarkdownCard and supports toggling raw mode', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => '# 投资分析报告\n\n| 指标 | 数值 |\n|---|---|\n| PE | 15.2 |',
      }),
    )

    const wrapper = mount(PreviewPane, {
      props: {
        artifact: {
          type: 'markdown',
          filePath: 'report.md',
          url: '/api/tasks/t1/artifacts/preview/report.md',
        },
      },
    })

    // Wait for fetch to complete and markdown to render
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('投资分析报告')
    })
    expect(wrapper.find('[data-test="toggle-raw-btn"]').exists()).toBe(true)

    // Toggle to raw mode
    await wrapper.find('[data-test="toggle-raw-btn"]').trigger('click')
    expect(wrapper.find('[data-test="markdown-raw"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="markdown-raw"]').text()).toContain('| PE | 15.2 |')

    // Toggle back to rendered mode
    await wrapper.find('[data-test="toggle-raw-btn"]').trigger('click')
    expect(wrapper.find('[data-test="markdown-rendered"]').exists()).toBe(true)
  })

  it('handles markdown fetch failure gracefully', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Network error')),
    )

    const wrapper = mount(PreviewPane, {
      props: {
        artifact: {
          type: 'markdown',
          filePath: 'broken.md',
          url: '/api/tasks/t1/artifacts/preview/broken.md',
        },
      },
    })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('（读取失败）')
    })
  })

  it('generates standalone preview URL for markdown artifacts in new tab link', () => {
    const wrapper = mount(PreviewPane, {
      props: {
        taskId: 't-123',
        artifact: {
          type: 'markdown',
          filePath: 'analysis.md',
          url: '/api/tasks/t-123/artifacts/preview/analysis.md',
        },
      },
    })

    const link = wrapper.find('[data-test="open-new-tab-link"]')
    expect(link.exists()).toBe(true)
    const href = link.attributes('href')
    expect(href).toContain('view=artifact')
    expect(href).toContain('taskId=t-123')
    expect(href).toContain('filePath=analysis.md')
  })

  it('uses direct URL for HTML artifacts in new tab link', () => {
    const wrapper = mount(PreviewPane, {
      props: {
        taskId: 't-123',
        artifact: {
          type: 'html',
          filePath: 'dashboard.html',
          url: '/api/tasks/t-123/artifacts/preview/dashboard.html',
        },
      },
    })

    const link = wrapper.find('[data-test="open-new-tab-link"]')
    expect(link.attributes('href')).toBe('/api/tasks/t-123/artifacts/preview/dashboard.html')
  })
})

describe('StandaloneArtifactViewer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads markdown and renders with McMarkdownCard', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => '## 财务分析核心摘要\n\n- ROE: 18%\n- 现金流稳健',
      }),
    )

    const wrapper = mount(StandaloneArtifactViewer, {
      props: {
        taskId: 'task-abc',
        filePath: 'summary.md',
      },
    })

    await vi.waitFor(() => {
      expect(wrapper.find('[data-test="standalone-rendered"]').exists()).toBe(true)
    })
    expect(wrapper.text()).toContain('财务分析核心摘要')
    expect(wrapper.text()).toContain('summary.md')

    // Test toggle raw mode
    await wrapper.find('[data-test="standalone-toggle-raw"]').trigger('click')
    expect(wrapper.find('[data-test="standalone-raw"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="standalone-raw"]').text()).toContain('ROE: 18%')

    // Test toggle back to rendered
    await wrapper.find('[data-test="standalone-toggle-raw"]').trigger('click')
    expect(wrapper.find('[data-test="standalone-rendered"]').exists()).toBe(true)
  })

  it('renders error state on network failure and allows retry', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new Error('Network error'))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(StandaloneArtifactViewer, {
      props: {
        taskId: 'task-abc',
        filePath: 'error.md',
      },
    })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('无法读取产物文件')
    })

    // Retry with successful response
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => '# 恢复成功',
    })
    await wrapper.find('.state-box.error button').trigger('click')

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('恢复成功')
    })
  })
})


