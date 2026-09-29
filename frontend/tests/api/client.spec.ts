import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiClient, ApiError } from '@/api/client'

describe('ApiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      }),
    )
    const client = new ApiClient('')
    expect(await client.get('/api/health')).toEqual({ status: 'ok' })
  })

  it('throws ApiError carrying the status code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'not found',
      }),
    )
    const client = new ApiClient('')
    await expect(client.get('/api/nope')).rejects.toBeInstanceOf(ApiError)
  })

  it('prefixes the base URL onto paths', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)
    const client = new ApiClient('http://api.test')
    await client.get('/api/health')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/health',
      expect.anything(),
    )
  })
})