import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { SynCodeBlock } from './SynCodeBlock'

describe('SynCodeBlock', () => {
  // Mock clipboard API - store ref to mock so we can assert on it
  const originalClipboard = navigator.clipboard
  let mockWriteText: ReturnType<typeof vi.fn>

  beforeEach(() => {
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
  // PF's ClipboardCopyButton tooltip is not reliably surfaced via userEvent in jsdom.
  it('shows "Copied to clipboard" after successful copy', async () => {
    render(<SynCodeBlock enableCopy>code</SynCodeBlock>)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    // eslint-disable-next-line testing-library/prefer-user-event -- userEvent does not trigger PF ClipboardCopyButton tooltip in jsdom
    fireEvent.click(copyButton)

    await waitFor(() => {
      expect(screen.getByText('Copied to clipboard')).toBeInTheDocument()
    })
  })

  it('copies JSON object to clipboard', async () => {
    const jsonObject = { test: 'value' }
    render(<SynCodeBlock enableCopy jsonObject={jsonObject} />)

    const copyButton = screen.getByRole('button', { name: 'Copy to clipboard' })
    // eslint-disable-next-line testing-library/prefer-user-event -- userEvent does not trigger PF ClipboardCopyButton tooltip in jsdom
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
