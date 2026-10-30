import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ShikiLanguage, ShikiTokenLines } from './shiki-service'
import { useSynCodeHighlight } from './useSynCodeHighlight'

const { mockHighlightCode, mockHighlightCodeSync, mockIsShikiReady, mockPreloadShiki, mockService } = vi.hoisted(() => {
  const mockHighlightCode = vi.fn<(source: string, language: ShikiLanguage) => Promise<ShikiTokenLines>>()
  const mockHighlightCodeSync = vi.fn<(source: string, language: ShikiLanguage) => ShikiTokenLines>()
  const mockIsShikiReady = vi.fn<(language?: ShikiLanguage) => boolean>()
  const mockPreloadShiki = vi.fn<(language?: ShikiLanguage) => Promise<void>>()
  const mockService = {
    highlightCode: mockHighlightCode,
    highlightCodeSync: mockHighlightCodeSync,
    isShikiReady: mockIsShikiReady,
    preloadShiki: mockPreloadShiki,
  }

  return { mockHighlightCode, mockHighlightCodeSync, mockIsShikiReady, mockPreloadShiki, mockService }
})

vi.mock('./shiki-service-loader', () => ({
  getLoadedShikiService: () => mockService,
  loadShikiService: () => Promise.resolve(mockService),
}))

describe('useSynCodeHighlight', () => {
  beforeEach(() => {
    mockHighlightCode.mockReset()
    mockHighlightCodeSync.mockReset()
    mockHighlightCodeSync.mockImplementation((source) =>
      source.split('\n').map((line) => [{ content: line, style: {} }])
    )
    mockIsShikiReady.mockReset()
    mockIsShikiReady.mockReturnValue(true)
    mockPreloadShiki.mockReset()
    mockPreloadShiki.mockResolvedValue(undefined)
  })

  it('returns tokenized source immediately when the shared highlighter is ready', () => {
    const source = '{\n  "status": "ready"\n}'
    const expectedTokens = source.split('\n').map((line) => [{ content: line, style: {} }])
    mockHighlightCodeSync.mockReturnValue(expectedTokens)

    const { result } = renderHook(() => useSynCodeHighlight(true, source, 'json', 'execution-1:node-1'))

    expect(result.current).toEqual({ status: 'ready', source, tokens: expectedTokens })
    expect(mockHighlightCodeSync).toHaveBeenCalledWith(source, 'json')
    expect(mockHighlightCode).not.toHaveBeenCalled()
  })

  it('keeps the source visible while the shared highlighter is not ready', async () => {
    mockIsShikiReady.mockReturnValue(false)
    mockPreloadShiki.mockRejectedValue(new Error('Shiki chunk unavailable'))

    const source = '{"status":"ready"}'
    const { result } = renderHook(() => useSynCodeHighlight(true, source, 'json', 'node-1'))

    expect(result.current).toEqual({ status: 'plain', source })
    await waitFor(() => expect(mockPreloadShiki).toHaveBeenCalledWith('json'))
    expect(result.current).toEqual({ status: 'plain', source })
  })
})
