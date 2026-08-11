import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { KeyValueFields } from './KeyValueFields'

describe('KeyValueFields', () => {
  it('renders add button with default label', () => {
    render(<KeyValueFields entries={[]} onChange={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add header' })).toBeInTheDocument()
  })

  it('renders add button with custom label', () => {
    render(<KeyValueFields entries={[]} onChange={vi.fn()} addButtonLabel="Add parameter" />)

    expect(screen.getByRole('button', { name: 'Add parameter' })).toBeInTheDocument()
  })

  it('clicking add button appends an empty row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<KeyValueFields entries={[]} onChange={handleChange} />)

    await user.click(screen.getByRole('button', { name: 'Add header' }))

    expect(handleChange).toHaveBeenCalledWith([expect.objectContaining({ key: '', value: '' })])
  })

  it('can type a header name', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<KeyValueFields entries={[{ id: 'h1', key: '', value: '' }]} onChange={handleChange} />)

    await user.type(screen.getByRole('textbox', { name: 'Header name 1' }), 'A')

    expect(handleChange).toHaveBeenCalledWith([{ id: 'h1', key: 'A', value: '' }])
  })

  it('updates only the changed key and preserves other entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'Accept', value: 'application/json' },
          { id: 'h2', key: 'User-Agent', value: 'Nexus' },
        ]}
        onChange={handleChange}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Header name/i })
    await user.type(nameInputs[0], 'X')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'AcceptX', value: 'application/json' },
      { id: 'h2', key: 'User-Agent', value: 'Nexus' },
    ])
  })

  it('can type a header value', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<KeyValueFields entries={[{ id: 'h1', key: 'Accept', value: '' }]} onChange={handleChange} />)

    await user.type(screen.getByRole('textbox', { name: 'Header value 1' }), 'j')

    expect(handleChange).toHaveBeenCalledWith([{ id: 'h1', key: 'Accept', value: 'j' }])
  })

  it('updates only the changed value and preserves other entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'Accept', value: 'application/json' },
          { id: 'h2', key: 'User-Agent', value: 'Nexus' },
        ]}
        onChange={handleChange}
      />
    )

    const valueInputs = screen.getAllByRole('textbox', { name: /Header value/i })
    await user.type(valueInputs[1], '!')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'Accept', value: 'application/json' },
      { id: 'h2', key: 'User-Agent', value: 'Nexus!' },
    ])
  })

  it('clicking remove button removes the row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'Accept', value: 'application/json' },
          { id: 'h2', key: 'User-Agent', value: 'Nexus' },
        ]}
        onChange={handleChange}
      />
    )

    const removeButtons = screen.getAllByRole('button', { name: /Remove header/i })
    await user.click(removeButtons[0])

    expect(handleChange).toHaveBeenCalledWith([{ id: 'h2', key: 'User-Agent', value: 'Nexus' }])
  })

  it('renders existing entries', () => {
    render(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'Accept', value: 'application/json' },
          { id: 'h2', key: 'Authorization', value: 'Bearer token' },
        ]}
        onChange={vi.fn()}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Header name/i })
    expect(nameInputs).toHaveLength(2)
    expect(nameInputs[0]).toHaveValue('Accept')
    expect(nameInputs[1]).toHaveValue('Authorization')

    const valueInputs = screen.getAllByRole('textbox', { name: /Header value/i })
    expect(valueInputs).toHaveLength(2)
    expect(valueInputs[0]).toHaveValue('application/json')
    expect(valueInputs[1]).toHaveValue('Bearer token')
  })

  it('hides add and remove buttons when disabled', () => {
    render(
      <KeyValueFields
        entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    expect(screen.queryByRole('button', { name: 'Add header' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove header/i })).not.toBeInTheDocument()
  })

  it('disables inputs when disabled', () => {
    render(
      <KeyValueFields
        entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    expect(screen.getByRole('textbox', { name: 'Header name 1' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Header value 1' })).toBeDisabled()
  })

  it('renders custom placeholders', () => {
    render(
      <KeyValueFields
        entries={[{ id: 'h1', key: '', value: '' }]}
        onChange={vi.fn()}
        keyPlaceholder="Param name"
        valuePlaceholder="Param value"
      />
    )

    expect(screen.getByPlaceholderText('Param name')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Param value')).toBeInTheDocument()
  })

  it('renders no rows when entries is empty', () => {
    render(<KeyValueFields entries={[]} onChange={vi.fn()} />)

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('removes the last remaining row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <KeyValueFields entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]} onChange={handleChange} />
    )

    await user.click(screen.getByRole('button', { name: /Remove header/i }))

    expect(handleChange).toHaveBeenCalledWith([])
  })

  it('adds a row when entries already exist', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <KeyValueFields entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]} onChange={handleChange} />
    )

    await user.click(screen.getByRole('button', { name: 'Add header' }))

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'Accept', value: 'application/json' },
      expect.objectContaining({ key: '', value: '' }),
    ])
  })

  it('renders default label and fieldId', () => {
    render(<KeyValueFields entries={[{ id: 'h1', key: '', value: '' }]} onChange={vi.fn()} />)

    expect(screen.getByText('Headers')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]} onChange={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(
      <KeyValueFields
        entries={[{ id: 'h1', key: 'Accept', value: 'application/json' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with empty entries', async () => {
    const { container } = render(<KeyValueFields entries={[]} onChange={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('callbacks work after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'Accept', value: 'json' }]} onChange={handleChange} />
    )

    rerender(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'Accept', value: 'json' },
          { id: 'h2', key: 'X-New', value: 'val' },
        ]}
        onChange={handleChange}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Add header' }))

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'Accept', value: 'json' },
      { id: 'h2', key: 'X-New', value: 'val' },
      expect.objectContaining({ key: '', value: '' }),
    ])
  })

  it('remove works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'A', value: '1' },
          { id: 'h2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const removeButtons = screen.getAllByRole('button', { name: /Remove header/i })
    await user.click(removeButtons[0])

    expect(handleChange).toHaveBeenCalledWith([{ id: 'h2', key: 'B', value: '2' }])
  })

  it('key change works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'A', value: '1' },
          { id: 'h2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Header name/i })
    await user.type(nameInputs[1], 'X')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'A', value: '1' },
      { id: 'h2', key: 'BX', value: '2' },
    ])
  })

  it('value change works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <KeyValueFields
        entries={[
          { id: 'h1', key: 'A', value: '1' },
          { id: 'h2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const valueInputs = screen.getAllByRole('textbox', { name: /Header value/i })
    await user.type(valueInputs[1], 'X')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'h1', key: 'A', value: '1' },
      { id: 'h2', key: 'B', value: '2X' },
    ])
  })

  it('transitions from disabled to enabled shows add and remove buttons', () => {
    const { rerender } = render(
      <KeyValueFields entries={[{ id: 'h1', key: 'A', value: '1' }]} onChange={vi.fn()} isDisabled />
    )

    expect(screen.queryByRole('button', { name: 'Add header' })).not.toBeInTheDocument()

    rerender(<KeyValueFields entries={[{ id: 'h1', key: 'A', value: '1' }]} onChange={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add header' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove header/i })).toBeInTheDocument()
  })
})
