import type { createHighlighterCore } from 'shiki/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Highlighter = Awaited<ReturnType<typeof createHighlighterCore>>

const { mockCreateHighlighterCore } = vi.hoisted(() => ({
  mockCreateHighlighterCore: vi.fn<typeof createHighlighterCore>(),
}))

vi.mock('shiki/core', () => ({ createHighlighterCore: mockCreateHighlighterCore }))
vi.mock('shiki/engine/javascript', () => ({ createJavaScriptRegexEngine: () => ({}) }))

function createDeferred<T>() {
  let rejectPromise: (reason?: unknown) => void = () => {}
  const promise = new Promise<T>((_resolve, reject) => {
    rejectPromise = reject
  })

  return { promise, reject: rejectPromise }
}

describe('shiki-service', () => {
  beforeEach(() => {
    vi.resetModules()
    mockCreateHighlighterCore.mockReset()
  })

  it('shares an in-flight initialization and allows another attempt after it fails', async () => {
    const firstInitialization = createDeferred<Highlighter>()
    mockCreateHighlighterCore
      .mockReturnValueOnce(firstInitialization.promise)
      .mockRejectedValueOnce(new Error('Shiki initialization failed'))

    const { preloadShiki } = await import('./shiki-service')
    const firstPreload = preloadShiki()
    const concurrentPreload = preloadShiki()

    expect(mockCreateHighlighterCore).toHaveBeenCalledOnce()

    firstInitialization.reject(new Error('Shiki initialization failed'))
    await expect(Promise.all([firstPreload, concurrentPreload])).rejects.toThrow('Shiki initialization failed')
    await expect(preloadShiki()).rejects.toThrow('Shiki initialization failed')

    expect(mockCreateHighlighterCore).toHaveBeenCalledTimes(2)
  })
})
