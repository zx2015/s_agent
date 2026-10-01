/**
 * Thin fetch wrapper for the backend REST API.
 *
 * A dedicated error type matters here: the workbench shows the user why a
 * pane is empty, and "request failed" is not an answer. Carrying the
 * status code lets callers distinguish "this task has no artifacts yet"
 * (404) from "the backend is down" (network error).
 */
import { parseSseFrame, splitSseBuffer } from './events'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class ApiClient {
  private readonly baseUrl: string

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`
  }

  async get<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path), {
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  async delete<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path), {
      method: 'DELETE',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      throw new ApiError(await response.text(), response.status)
    }
    return (await response.json()) as T
  }

  /**
   * POST a message and consume the response as a stream of parsed SSE frames.
   *
   * @param path - The endpoint path.
   * @param body - The JSON request body.
   * @returns An async generator yielding parsed frames in arrival order.
   */
  async *stream(
    path: string,
    body: unknown,
    signal?: AbortSignal,
  ): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
    const response = await fetch(this.url(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
      signal,
    })

    if (!response.ok || !response.body) {
      throw new ApiError(await response.text(), response.status)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const { frames, rest } = splitSseBuffer(buffer)
      buffer = rest

      for (const frame of frames) {
        const parsed = parseSseFrame(frame)
        if (parsed) yield parsed
      }
    }
  }

  /**
   * GET an SSE stream and consume the response as parsed frames.
   *
   * Used for reconnecting to an ongoing background task turn.
   *
   * @param path - The endpoint path.
   * @param signal - Optional AbortSignal.
   * @returns An async generator yielding parsed frames in arrival order.
   */
  async *streamGet(
    path: string,
    signal?: AbortSignal,
  ): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
    const response = await fetch(this.url(path), {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
      },
      signal,
    })

    if (!response.ok || !response.body) {
      throw new ApiError(await response.text(), response.status)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const { frames, rest } = splitSseBuffer(buffer)
      buffer = rest

      for (const frame of frames) {
        const parsed = parseSseFrame(frame)
        if (parsed) yield parsed
      }
    }
  }
}

export const apiClient = new ApiClient('')