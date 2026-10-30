import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { OutputJsonView } from './OutputJsonView'

async function expectCodeBlockToContain(content: string): Promise<void> {
  await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent(content))
}

describe('OutputJsonView', () => {
  const originalClipboard = navigator.clipboard
  let mockWriteText: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockWriteText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
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

  it('renders pretty-printed JSON from data prop', async () => {
    const data = { name: 'test', value: 42 }
    render(<OutputJsonView data={data} />)

    await expectCodeBlockToContain('"name": "test"')
    await expectCodeBlockToContain('"value": 42')
  })

  it('copies JSON to clipboard when copy button is clicked', async () => {
    // userEvent.setup() replaces navigator.clipboard, so re-apply the mock after setup
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
      writable: true,
      configurable: true,
    })

    const data = { greeting: 'hello' }
    render(<OutputJsonView data={data} />)

    await user.click(screen.getByRole('button', { name: /copy to clipboard/i }))

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith(JSON.stringify(data, null, 2))
    })
  })

  it('handles null data gracefully', () => {
    render(<OutputJsonView data={null} />)

    expect(screen.queryByRole('textbox', { name: 'Search json output' })).not.toBeInTheDocument()
  })

  it('renders with a search input', () => {
    const data = { key: 'value' }
    render(<OutputJsonView data={data} />)

    expect(screen.getByRole('textbox', { name: 'Search json output' })).toBeInTheDocument()
  })

  it('filters lines when searching', async () => {
    const user = userEvent.setup()
    const data = { greeting: 'hello', farewell: 'goodbye' }
    render(<OutputJsonView data={data} />)

    const searchInput = screen.getByRole('textbox', { name: 'Search json output' })
    await user.type(searchInput, 'greeting')

    await expectCodeBlockToContain('"greeting"')
    expect(screen.getByRole('code')).not.toHaveTextContent('"farewell"')
  })

  it('has no accessibility violations', async () => {
    const data = { name: 'test', value: 42 }
    const { container } = render(<OutputJsonView data={data} />)

    await expectCodeBlockToContain('"name": "test"')
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with null data', async () => {
    const { container } = render(<OutputJsonView data={null} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
