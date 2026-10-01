/**
 * Global vitest setup.
 *
 * jsdom doesn't implement `ResizeObserver` — real browsers do, but
 * @matechat/core's `McLayoutContent` (used by SidebarMiddle.vue for the
 * chat scroll area) constructs one unconditionally in `setup()` to
 * auto-scroll on content growth. Without this stub, mounting anything
 * that nests `McLayoutContent` throws `ReferenceError: ResizeObserver is
 * not defined` before a single assertion runs.
 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}

beforeEach(() => {
  if (typeof localStorage !== 'undefined') {
    localStorage.clear()
  }
  if (typeof window !== 'undefined' && window.history?.replaceState) {
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('taskId')
      window.history.replaceState({}, '', url.toString())
    } catch {}
  }
})
