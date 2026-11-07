import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { InputJsonView } from './InputJsonView'

describe('InputJsonView', () => {
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
    render(<InputJsonView data={data} />)

    await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent('"name": "test"'))
    await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent('"value": 42'))
  })

  it('copies JSON to clipboard when copy button is clicked', async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
      writable: true,
      configurable: true,
    })

    const data = { greeting: 'hello' }
    render(<InputJsonView data={data} />)

    await user.click(screen.getByRole('button', { name: /copy to clipboard/i }))

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith(JSON.stringify(data, null, 2))
    })
  })

  it('handles null data by rendering nothing', () => {
    render(<InputJsonView data={null} />)

    expect(screen.queryByRole('region', { name: 'JSON input' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /copy to clipboard/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const data = { name: 'test', value: 42 }
    const { container } = render(<InputJsonView data={data} />)

    await waitFor(() => expect(screen.getByRole('code')).toHaveTextContent('"name": "test"'))
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with null data', async () => {
    const { container } = render(<InputJsonView data={null} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
