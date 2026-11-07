import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import type { ShikiLanguage, ShikiTokenLines } from './shiki-service'
import { SynCodeBlock } from './SynCodeBlock'

const {
  mockHighlightCode,
  mockHighlightCodeSync,
  mockIsShikiReady,
  mockPreloadShiki,
  mockLoadShikiService,
  mockService,
} = vi.hoisted(() => {
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

  return {
    mockHighlightCode,
    mockHighlightCodeSync,
    mockIsShikiReady,
    mockPreloadShiki,
    mockLoadShikiService: vi.fn<() => Promise<typeof mockService>>(),
    mockService,
  }
})

vi.mock('./shiki-service-loader', () => ({
  getLoadedShikiService: () => mockService,
  loadShikiService: mockLoadShikiService,
}))

function createDeferred<T>() {
  let resolvePromise: (value: T) => void = () => {}
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve
  })

  return { promise, resolve: (value: T) => resolvePromise(value) }
}

function createTokenLines(source: string): ShikiTokenLines {
  return source.split('\n').map((line) => [{ content: line, style: {} }])
}

function getCodeTexts(): string[] {
  return screen.getAllByRole('code', { hidden: true }).map((code) => code.textContent ?? '')
}

describe('SynCodeBlock', () => {
  // Mock clipboard API - store ref to mock so we can assert on it
  const originalClipboard = navigator.clipboard
  let mockWriteText: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockHighlightCode.mockReset()
    mockHighlightCode.mockImplementation((source) => Promise.resolve(createTokenLines(source)))
    mockHighlightCodeSync.mockReset()
    mockHighlightCodeSync.mockImplementation((source) => createTokenLines(source))
    mockIsShikiReady.mockReset()
    mockIsShikiReady.mockReturnValue(false)
    mockPreloadShiki.mockReset()
    mockPreloadShiki.mockResolvedValue(undefined)
    mockLoadShikiService.mockReset()
    mockLoadShikiService.mockResolvedValue(mockService)
    mockWriteText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: mockWriteText,
      },
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      writable: true,
      configurable: true,
    })
    vi.restoreAllMocks()
  })

  it('renders string children', () => {
    render(<SynCodeBlock>console.log('hello')</SynCodeBlock>)

    expect(screen.getByText("console.log('hello')")).toBeInTheDocument()
    expect(mockHighlightCode).not.toHaveBeenCalled()
  })

  it('uses the selected language for highlighting', () => {
    mockIsShikiReady.mockReturnValue(true)
    const source = 'curl --version'

    render(<SynCodeBlock language="bash">{source}</SynCodeBlock>)

    expect(mockHighlightCodeSync).toHaveBeenCalledWith(source, 'bash')
  })

  describe('syntax highlighting', () => {
    it('shows plain source immediately while highlighting completes', async () => {
      const source = '{\n  "name": "runner"\n}'
      const pendingHighlight = createDeferred<ShikiTokenLines>()
      mockIsShikiReady.mockReturnValue(false)
      mockHighlightCode.mockReturnValueOnce(pendingHighlight.promise)

      render(<SynCodeBlock language="json">{source}</SynCodeBlock>)

      expect(getCodeTexts()).toEqual([source])
      expect(screen.queryByRole('status')).not.toBeInTheDocument()

      const highlightedTokens = source.split('\n').map((line) => [{ content: line, style: { color: 'rgb(1, 2, 3)' } }])
      await act(async () => {
        pendingHighlight.resolve(highlightedTokens)
        await pendingHighlight.promise
      })

      await waitFor(() => expect(screen.getByText(/"name": "runner"/)).toHaveStyle({ color: 'rgb(1, 2, 3)' }))
    })

    it('renders highlighted output on the first frame when Shiki was preloaded', () => {
      const source = '{\n  "name": "runner"\n}'
      mockIsShikiReady.mockReturnValue(true)

      render(<SynCodeBlock language="json">{source}</SynCodeBlock>)

      expect(getCodeTexts()).toEqual([source])
      expect(mockHighlightCodeSync).toHaveBeenCalledWith(source, 'json')
      expect(mockHighlightCode).not.toHaveBeenCalled()
    })

    it('keeps visible, copied, and expanded content together during a same-node refresh', async () => {
      const previousSource = '{\n  "status": "running"\n}'
      const updatedSource = '{\n  "status": "completed"\n}'
      const pendingUpdate = createDeferred<ShikiTokenLines>()
      mockHighlightCode.mockResolvedValueOnce(createTokenLines(previousSource))
      mockHighlightCode.mockReturnValueOnce(pendingUpdate.promise)

      const { rerender } = render(
        <SynCodeBlock language="json" highlightKey="execution-1:node-1" enableCopy enableExpand>
          {previousSource}
        </SynCodeBlock>
      )
      await waitFor(() => expect(getCodeTexts()).toEqual([previousSource]))

      await userEvent.click(screen.getByRole('button', { name: 'Copy to clipboard' }))
      expect(mockWriteText).toHaveBeenLastCalledWith(previousSource)
      await userEvent.click(screen.getByRole('button', { name: 'Expand code' }))
      await waitFor(() => expect(getCodeTexts()).toEqual([previousSource, previousSource]))

      rerender(
        <SynCodeBlock language="json" highlightKey="execution-1:node-1" enableCopy enableExpand>
          {updatedSource}
        </SynCodeBlock>
      )

      expect(getCodeTexts()).toEqual([previousSource, previousSource])
      await userEvent.click(screen.getAllByRole('button', { name: 'Copy to clipboard' })[0])
      expect(mockWriteText).toHaveBeenLastCalledWith(previousSource)

      await act(async () => {
        pendingUpdate.resolve(createTokenLines(updatedSource))
        await pendingUpdate.promise
      })

      await waitFor(() => expect(getCodeTexts()).toEqual([updatedSource, updatedSource]))
      await userEvent.click(screen.getAllByRole('button', { name: 'Copy to clipboard' })[0])
      expect(mockWriteText).toHaveBeenLastCalledWith(updatedSource)
    })

    it('does not retain or copy a previous selection while a new node is highlighting', async () => {
      const previousSource = '{\n  "node": "previous"\n}'
      const currentSource = '{\n  "node": "current"\n}'
      const previousHighlight = createDeferred<ShikiTokenLines>()
      const currentHighlight = createDeferred<ShikiTokenLines>()
      mockHighlightCode.mockReturnValueOnce(previousHighlight.promise).mockReturnValueOnce(currentHighlight.promise)

      const { rerender } = render(
        <SynCodeBlock language="json" highlightKey="execution-1:node-1" enableCopy>
          {previousSource}
        </SynCodeBlock>
      )
      await waitFor(() => expect(mockHighlightCode).toHaveBeenCalledTimes(1))

      rerender(
        <SynCodeBlock language="json" highlightKey="execution-2:node-2" enableCopy>
          {currentSource}
        </SynCodeBlock>
      )

      expect(getCodeTexts()).toEqual([currentSource])
      await userEvent.click(screen.getByRole('button', { name: 'Copy to clipboard' }))
      expect(mockWriteText).toHaveBeenLastCalledWith(currentSource)

      await act(async () => {
        previousHighlight.resolve(createTokenLines(previousSource))
        await previousHighlight.promise
      })
      expect(getCodeTexts()).toEqual([currentSource])

      await act(async () => {
        currentHighlight.resolve(createTokenLines(currentSource))
        await currentHighlight.promise
      })
      await waitFor(() => expect(getCodeTexts()).toEqual([currentSource]))
    })

    it('falls back to current plain source with search, copy, and expand after highlighting fails', async () => {
      const source = '{\n  "status": "failed"\n}'
      mockHighlightCode.mockRejectedValueOnce(new Error('Shiki failed'))

      render(
        <SynCodeBlock language="json" searchTerm="FAILED" enableCopy enableExpand>
          {source}
        </SynCodeBlock>
      )

      await waitFor(() => expect(getCodeTexts()).toEqual([source]))
      expect(screen.getByRole('mark')).toHaveTextContent('failed')
      await userEvent.click(screen.getByRole('button', { name: 'Copy to clipboard' }))
      expect(mockWriteText).toHaveBeenLastCalledWith(source)

      await userEvent.click(screen.getByRole('button', { name: 'Expand code' }))
      await waitFor(() => expect(getCodeTexts()).toEqual([source, source]))
    })

    it('marks matches that cross token boundaries and preserves exact source whitespace', async () => {
      const source = '{\n  "status": "failed"\n}'
      const matchingTokens: ShikiTokenLines = [
        [{ content: '{', style: {} }],
        [
          { content: '  ', style: {} },
          { content: '"', style: {} },
          { content: 'status', style: {} },
          { content: '"', style: {} },
          { content: ': ', style: {} },
          { content: '"', style: {} },
          { content: 'failed', style: {} },
          { content: '"', style: {} },
        ],
        [{ content: '}', style: {} }],
      ]
      mockHighlightCode.mockResolvedValueOnce(matchingTokens)

      render(
        <SynCodeBlock language="json" searchTerm={'"STATUS": "FAILED"'} enableCopy>
          {source}
        </SynCodeBlock>
      )

      await waitFor(() => expect(screen.getAllByRole('mark').length).toBeGreaterThan(0))
      expect(
        screen
          .getAllByRole('mark')
          .map((mark) => mark.textContent)
          .join('')
      ).toBe('"status": "failed"')
      expect(getCodeTexts()).toEqual([source])

      await userEvent.click(screen.getByRole('button', { name: 'Copy to clipboard' }))
      expect(mockWriteText).toHaveBeenLastCalledWith(source)
    })
  })

  it('renders JSON object formatted', () => {
    const jsonObject = { name: 'test', value: 123 }
    render(<SynCodeBlock jsonObject={jsonObject} />)

    expect(screen.getByText(/"name": "test"/)).toBeInTheDocument()
    expect(screen.getByText(/"value": 123/)).toBeInTheDocument()
  })

  it('renders as PatternFly CodeBlock', () => {
    render(<SynCodeBlock>code</SynCodeBlock>)

    // PF CodeBlock renders content inside a <code> element
    expect(screen.getByText('code').tagName.toLowerCase()).toBe('code')
  })

  it('does not show copy button by default', () => {
    render(<SynCodeBlock>code</SynCodeBlock>)

    expect(screen.queryByRole('button', { name: 'Copy to clipboard' })).not.toBeInTheDocument()
  })

  it('shows copy button when enableCopy is true', () => {
    render(<SynCodeBlock enableCopy>code</SynCodeBlock>)

    expect(screen.getByRole('button', { name: 'Copy to clipboard' })).toBeInTheDocument()
  })

  it('copies text to clipboard when copy button clicked', async () => {
    render(<SynCodeBlock enableCopy>code to copy</SynCodeBlock>)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    await userEvent.click(copyButton)

    expect(mockWriteText).toHaveBeenCalledWith('code to copy')
  })

  // fireEvent.click is required here: userEvent's internal scheduler advances setTimeout,
  // which fires the setIsCopied(false) reset before waitFor can observe the tooltip text.
  // PF's ClipboardCopyButton tooltip is not reliably surfaced via userEvent in happy-dom.
  it('shows "Copied to clipboard" after successful copy', async () => {
    render(<SynCodeBlock enableCopy>code</SynCodeBlock>)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    // eslint-disable-next-line testing-library/prefer-user-event -- userEvent does not trigger PF ClipboardCopyButton tooltip in happy-dom
    fireEvent.click(copyButton)

    await waitFor(() => {
      expect(screen.getByText('Copied to clipboard')).toBeInTheDocument()
    })
  })

  it('copies JSON object to clipboard', async () => {
    const jsonObject = { test: 'value' }
    render(<SynCodeBlock enableCopy jsonObject={jsonObject} />)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    // eslint-disable-next-line testing-library/prefer-user-event -- userEvent does not trigger PF ClipboardCopyButton tooltip in happy-dom
    fireEvent.click(copyButton)

    // waitFor absorbs the setIsCopied(true) microtask (queued via detachPromise) inside act()
    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith(JSON.stringify(jsonObject, undefined, 2))
    })
  })

  it('does not show success label when clipboard write fails', async () => {
    const rejectWriteText = vi.fn().mockRejectedValue(new Error('Clipboard error'))
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: rejectWriteText,
      },
      writable: true,
      configurable: true,
    })

    render(<SynCodeBlock enableCopy>code</SynCodeBlock>)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    // Static userEvent.click (no userEvent.setup()) avoids TL replacing navigator.clipboard with its stub.
    await userEvent.click(copyButton)

    await waitFor(() => {
      expect(rejectWriteText).toHaveBeenCalledWith('code')
    })
    await Promise.resolve()
    expect(screen.queryByText('Copied to clipboard')).not.toBeInTheDocument()
    expect(copyButton).toHaveAccessibleName('Copy to clipboard')
  })

  it('renders children over jsonObject when both provided', () => {
    render(<SynCodeBlock jsonObject={{ ignored: true }}>preferred content</SynCodeBlock>)

    expect(screen.getByText('preferred content')).toBeInTheDocument()
    expect(screen.queryByText('ignored')).not.toBeInTheDocument()
  })

  it('handles empty content gracefully', () => {
    expect(() => render(<SynCodeBlock />)).not.toThrow()
  })

  it('does not copy when clipboard is unavailable', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      writable: true,
      configurable: true,
    })

    render(<SynCodeBlock enableCopy>code</SynCodeBlock>)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    await expect(userEvent.click(copyButton)).resolves.toBeUndefined()
  })

  describe('expand modal', () => {
    it('does not render expand button by default', () => {
      render(<SynCodeBlock>code</SynCodeBlock>)

      expect(screen.queryByRole('button', { name: 'Expand code' })).not.toBeInTheDocument()
    })

    it('renders expand button when enableExpand is true', () => {
      render(<SynCodeBlock enableExpand>code</SynCodeBlock>)

      expect(screen.getByRole('button', { name: 'Expand code' })).toBeInTheDocument()
    })

    it('opens modal when expand button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <SynCodeBlock enableExpand expandTitle="Output JSON">
          code content
        </SynCodeBlock>
      )

      await user.click(screen.getByRole('button', { name: 'Expand code' }))

      expect(screen.getByRole('dialog', { name: 'Output JSON' })).toBeInTheDocument()
      expect(screen.getAllByText('code content').length).toBeGreaterThan(0)
    })

    it('closes modal when X button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <SynCodeBlock enableExpand expandTitle="Output JSON">
          code content
        </SynCodeBlock>
      )

      await user.click(screen.getByRole('button', { name: 'Expand code' }))
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Close' }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('shows copy button inside modal when enableCopy is true', async () => {
      const user = userEvent.setup()
      render(
        <SynCodeBlock enableExpand enableCopy expandTitle="Output JSON">
          code content
        </SynCodeBlock>
      )

      await user.click(screen.getByRole('button', { name: 'Expand code' }))

      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      // copy button is inside the modal's PFCodeBlock actions, not in a footer
      const copyButtons = screen.getAllByRole('button', { name: 'Copy to clipboard' })
      expect(copyButtons.length).toBeGreaterThan(0)
    })

    it('modal has no footer element', async () => {
      const user = userEvent.setup()
      render(
        <SynCodeBlock enableExpand expandTitle="Output JSON">
          code
        </SynCodeBlock>
      )

      await user.click(screen.getByRole('button', { name: 'Expand code' }))

      const dialog = screen.getByRole('dialog', { name: 'Output JSON' })
      // Only the header Close button should be present — no footer buttons
      const buttons = within(dialog).getAllByRole('button')
      expect(buttons).toHaveLength(1)
      expect(buttons[0]).toHaveAccessibleName('Close')
    })
  })
})
