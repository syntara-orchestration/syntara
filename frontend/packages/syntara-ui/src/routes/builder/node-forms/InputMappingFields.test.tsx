import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { InputMappingFields } from './InputMappingFields'

describe('InputMappingFields', () => {
  it('renders add button with correct label', () => {
    render(<InputMappingFields entries={[]} onChange={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add input mapping' })).toBeInTheDocument()
  })

  it('clicking add button appends an empty row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<InputMappingFields entries={[]} onChange={handleChange} />)

    await user.click(screen.getByRole('button', { name: 'Add input mapping' }))

    expect(handleChange).toHaveBeenCalledWith([expect.objectContaining({ key: '', value: '' })])
  })

  it('can type a child input name', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<InputMappingFields entries={[{ id: 'i1', key: '', value: '' }]} onChange={handleChange} />)

    await user.type(screen.getByRole('textbox', { name: 'Child input name 1' }), 'target_host')

    expect(handleChange).toHaveBeenCalledWith([{ id: 'i1', key: 'target_host', value: '' }])
  })

  it('updates only the changed key and preserves other entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'host', value: '${ inventory_host }' },
          { id: 'i2', key: 'port', value: '22' },
        ]}
        onChange={handleChange}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Child input name/i })
    await user.type(nameInputs[0], '_name')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'host_name', value: '${ inventory_host }' },
      { id: 'i2', key: 'port', value: '22' },
    ])
  })

  it('can type a parent value', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<InputMappingFields entries={[{ id: 'i1', key: 'target', value: '' }]} onChange={handleChange} />)

    await user.type(screen.getByRole('textbox', { name: 'Parent value 1' }), '${ parent_var }')

    expect(handleChange).toHaveBeenCalledWith([{ id: 'i1', key: 'target', value: '${ parent_var }' }])
  })

  it('updates only the changed value and preserves other entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'host', value: '${ inventory_host }' },
          { id: 'i2', key: 'port', value: '22' },
        ]}
        onChange={handleChange}
      />
    )

    const valueInputs = screen.getAllByRole('textbox', { name: /Parent value/i })
    await user.type(valueInputs[1], '3')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'host', value: '${ inventory_host }' },
      { id: 'i2', key: 'port', value: '223' },
    ])
  })

  it('clicking remove button removes the row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'host', value: '${ inventory_host }' },
          { id: 'i2', key: 'port', value: '22' },
        ]}
        onChange={handleChange}
      />
    )

    const removeButtons = screen.getAllByRole('button', { name: /Remove input mapping/i })
    await user.click(removeButtons[0])

    expect(handleChange).toHaveBeenCalledWith([{ id: 'i2', key: 'port', value: '22' }])
  })

  it('renders existing entries', () => {
    render(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'target_host', value: '${ inventory_host }' },
          { id: 'i2', key: 'port', value: '22' },
        ]}
        onChange={vi.fn()}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Child input name/i })
    expect(nameInputs).toHaveLength(2)
    expect(nameInputs[0]).toHaveValue('target_host')
    expect(nameInputs[1]).toHaveValue('port')

    const valueInputs = screen.getAllByRole('textbox', { name: /Parent value/i })
    expect(valueInputs).toHaveLength(2)
    expect(valueInputs[0]).toHaveValue('${ inventory_host }')
    expect(valueInputs[1]).toHaveValue('22')
  })

  it('hides add and remove buttons when disabled', () => {
    render(
      <InputMappingFields
        entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    expect(screen.queryByRole('button', { name: 'Add input mapping' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove input mapping/i })).not.toBeInTheDocument()
  })

  it('disables inputs when disabled', () => {
    render(
      <InputMappingFields
        entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    expect(screen.getByRole('textbox', { name: 'Child input name 1' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Parent value 1' })).toBeDisabled()
  })

  it('renders correct placeholders', () => {
    render(<InputMappingFields entries={[{ id: 'i1', key: '', value: '' }]} onChange={vi.fn()} />)

    expect(screen.getByPlaceholderText('Child input name')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Parent value or ${ expression }')).toBeInTheDocument()
  })

  it('renders no rows when entries is empty', () => {
    render(<InputMappingFields entries={[]} onChange={vi.fn()} />)

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('removes the last remaining row', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <InputMappingFields entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]} onChange={handleChange} />
    )

    await user.click(screen.getByRole('button', { name: /Remove input mapping/i }))

    expect(handleChange).toHaveBeenCalledWith([])
  })

  it('adds a row when entries already exist', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(
      <InputMappingFields entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]} onChange={handleChange} />
    )

    await user.click(screen.getByRole('button', { name: 'Add input mapping' }))

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'host', value: '${ inventory_host }' },
      expect.objectContaining({ key: '', value: '' }),
    ])
  })

  it('renders correct label and fieldId', () => {
    render(<InputMappingFields entries={[{ id: 'i1', key: '', value: '' }]} onChange={vi.fn()} />)

    expect(screen.getByText('Input Mapping')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]} onChange={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = render(
      <InputMappingFields
        entries={[{ id: 'i1', key: 'host', value: '${ inventory_host }' }]}
        onChange={vi.fn()}
        isDisabled
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with empty entries', async () => {
    const { container } = render(<InputMappingFields entries={[]} onChange={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('callbacks work after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'host', value: '${ var }' }]} onChange={handleChange} />
    )

    rerender(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'host', value: '${ var }' },
          { id: 'i2', key: 'port', value: '22' },
        ]}
        onChange={handleChange}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Add input mapping' }))

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'host', value: '${ var }' },
      { id: 'i2', key: 'port', value: '22' },
      expect.objectContaining({ key: '', value: '' }),
    ])
  })

  it('remove works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'A', value: '1' },
          { id: 'i2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const removeButtons = screen.getAllByRole('button', { name: /Remove input mapping/i })
    await user.click(removeButtons[0])

    expect(handleChange).toHaveBeenCalledWith([{ id: 'i2', key: 'B', value: '2' }])
  })

  it('key change works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'A', value: '1' },
          { id: 'i2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const nameInputs = screen.getAllByRole('textbox', { name: /Child input name/i })
    await user.type(nameInputs[1], 'X')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'A', value: '1' },
      { id: 'i2', key: 'BX', value: '2' },
    ])
  })

  it('value change works after re-render with updated entries', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const { rerender } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'A', value: '1' }]} onChange={handleChange} />
    )

    rerender(
      <InputMappingFields
        entries={[
          { id: 'i1', key: 'A', value: '1' },
          { id: 'i2', key: 'B', value: '2' },
        ]}
        onChange={handleChange}
      />
    )

    const valueInputs = screen.getAllByRole('textbox', { name: /Parent value/i })
    await user.type(valueInputs[1], 'X')

    expect(handleChange).toHaveBeenCalledWith([
      { id: 'i1', key: 'A', value: '1' },
      { id: 'i2', key: 'B', value: '2X' },
    ])
  })

  it('transitions from disabled to enabled shows add and remove buttons', () => {
    const { rerender } = render(
      <InputMappingFields entries={[{ id: 'i1', key: 'A', value: '1' }]} onChange={vi.fn()} isDisabled />
    )

    expect(screen.queryByRole('button', { name: 'Add input mapping' })).not.toBeInTheDocument()

    rerender(<InputMappingFields entries={[{ id: 'i1', key: 'A', value: '1' }]} onChange={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add input mapping' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove input mapping/i })).toBeInTheDocument()
  })
})
