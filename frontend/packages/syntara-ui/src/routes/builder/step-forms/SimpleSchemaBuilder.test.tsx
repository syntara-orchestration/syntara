import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { generateUUID } from '../../../utils/generateUUID'

import { SimpleSchemaBuilder } from './SimpleSchemaBuilder'
import { type SimpleField } from './simpleSchemaUtils'

function makeField(overrides: Partial<SimpleField> = {}): SimpleField {
  return { id: generateUUID(), name: '', type: 'string', required: false, ...overrides }
}

describe('SimpleSchemaBuilder', () => {
  it('renders the Add field button when no fields exist', () => {
    render(<SimpleSchemaBuilder fields={[]} onFieldsChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Add field' })).toBeInTheDocument()
  })

  it('calls onFieldsChange with a new field when Add field is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SimpleSchemaBuilder fields={[]} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add field' }))

    expect(onChange).toHaveBeenCalledTimes(1)
    const newFields = onChange.mock.calls[0][0] as SimpleField[]
    expect(newFields).toHaveLength(1)
    expect(newFields[0].name).toBe('')
    expect(newFields[0].type).toBe('string')
    expect(newFields[0].required).toBe(false)
  })

  it('renders existing fields with name, type, required, and remove controls', () => {
    const fields = [makeField({ id: '1', name: 'event', type: 'string', required: true })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('event')
    expect(screen.getByText('String')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Required' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Remove field event' })).toBeInTheDocument()
  })

  it('calls onFieldsChange with updated name, preserving other fields unchanged', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'first' }), makeField({ id: '2', name: 'second' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    const input = screen.getByRole('textbox', { name: 'Field name 1' })
    await user.type(input, 'x')

    const updatedFields = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(updatedFields[0].name).toBe('firstx')
    expect(updatedFields[1].name).toBe('second')
    expect(updatedFields[1].id).toBe('2')
  })

  it('calls onFieldsChange with updated required when checkbox is toggled', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'event', required: false })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('checkbox', { name: 'Required' }))

    const lastCall = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(lastCall[0].required).toBe(true)
  })

  it('calls onFieldsChange without the field when remove is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'keep' }), makeField({ id: '2', name: 'remove' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Remove field remove' }))

    const lastCall = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(lastCall).toHaveLength(1)
    expect(lastCall[0].name).toBe('keep')
  })

  it('opens the type dropdown and selects a different type', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'count', type: 'string' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'String' }))
    await user.click(screen.getByRole('option', { name: 'Integer' }))

    const lastCall = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(lastCall[0].type).toBe('integer')
  })

  it('renders multiple field rows', () => {
    const fields = [
      makeField({ id: '1', name: 'event' }),
      makeField({ id: '2', name: 'count' }),
      makeField({ id: '3', name: 'active' }),
    ]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('event')
    expect(screen.getByRole('textbox', { name: 'Field name 2' })).toHaveValue('count')
    expect(screen.getByRole('textbox', { name: 'Field name 3' })).toHaveValue('active')
  })

  it('uses index-based remove label for unnamed fields', () => {
    const fields = [makeField({ id: '1', name: '' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Remove field 1' })).toBeInTheDocument()
  })

  it('renders the correct type label for non-string types', () => {
    const fields = [
      makeField({ id: '1', name: 'count', type: 'integer' }),
      makeField({ id: '2', name: 'ratio', type: 'number' }),
      makeField({ id: '3', name: 'active', type: 'boolean' }),
    ]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)

    expect(screen.getByText('Integer')).toBeInTheDocument()
    expect(screen.getByText('Number')).toBeInTheDocument()
    expect(screen.getByText('Boolean')).toBeInTheDocument()
  })

  it('calls onFieldsChange when selecting a different type from the dropdown', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'field', type: 'string' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'String' }))
    await user.click(screen.getByRole('option', { name: 'Boolean' }))

    const lastCall = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(lastCall[0].type).toBe('boolean')
  })

  it('shows all four type options in the dropdown', async () => {
    const user = userEvent.setup()
    const fields = [makeField({ id: '1', name: 'field' })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'String' }))

    expect(screen.getByRole('option', { name: 'String' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Number' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Integer' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Boolean' })).toBeInTheDocument()
  })

  it('exercises all FieldRow controls on a single field', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'status', type: 'boolean', required: true })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('status')
    expect(screen.getByText('Boolean')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Required' })).toBeChecked()

    await user.click(screen.getByRole('checkbox', { name: 'Required' }))
    const afterToggle = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(afterToggle[0].required).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Remove field status' }))
    const afterRemove = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(afterRemove).toHaveLength(0)
  })

  it('renders a single field with default string type unchecked', () => {
    const fields = [makeField({ id: '1', name: 'x', type: 'string', required: false })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)
    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('x')
    expect(screen.getByRole('checkbox', { name: 'Required' })).not.toBeChecked()
  })

  it('renders a field with number type checked', () => {
    const fields = [makeField({ id: '1', name: 'amt', type: 'number', required: true })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)
    expect(screen.getByText('Number')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Required' })).toBeChecked()
  })

  it('renders a field with boolean type', () => {
    const fields = [makeField({ id: '1', name: 'flag', type: 'boolean', required: false })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)
    expect(screen.getByText('Boolean')).toBeInTheDocument()
  })

  it('renders a field with integer type', () => {
    const fields = [makeField({ id: '1', name: 'n', type: 'integer', required: true })]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)
    expect(screen.getByText('Integer')).toBeInTheDocument()
  })

  it('renders empty state then adds a field', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<SimpleSchemaBuilder fields={[]} onFieldsChange={onChange} />)

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add field' }))

    const newFields = onChange.mock.calls[0][0] as SimpleField[]
    rerender(<SimpleSchemaBuilder fields={newFields} onFieldsChange={onChange} />)
    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toBeInTheDocument()
  })

  it('selects each type option sequentially', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'f', type: 'string' })]

    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    for (const typeName of ['Number', 'Integer', 'Boolean', 'String']) {
      await user.click(screen.getByRole('button', { name: /String|Number|Integer|Boolean/ }))
      await user.click(screen.getByRole('option', { name: typeName }))
    }
    expect(onChange).toHaveBeenCalled()
  })

  it('removes a field from the middle of the list', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [
      makeField({ id: '1', name: 'a' }),
      makeField({ id: '2', name: 'b' }),
      makeField({ id: '3', name: 'c' }),
    ]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Remove field b' }))

    const result = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(result).toHaveLength(2)
    expect(result[0].name).toBe('a')
    expect(result[1].name).toBe('c')
  })

  it('re-renders when fields prop changes from empty to populated', () => {
    const onChange = vi.fn()
    const { rerender } = render(<SimpleSchemaBuilder fields={[]} onFieldsChange={onChange} />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    const fields = [
      makeField({ id: '1', name: 'a', type: 'string', required: false }),
      makeField({ id: '2', name: 'b', type: 'integer', required: true }),
    ]
    rerender(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)
    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('a')
    expect(screen.getByRole('textbox', { name: 'Field name 2' })).toHaveValue('b')
  })

  it('re-renders when fields prop changes from populated to empty', () => {
    const onChange = vi.fn()
    const fields = [makeField({ id: '1', name: 'x', type: 'boolean', required: true })]
    const { rerender } = render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)
    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toHaveValue('x')

    rerender(<SimpleSchemaBuilder fields={[]} onFieldsChange={onChange} />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('updates field via checkbox toggle in a multi-field list', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [
      makeField({ id: '1', name: 'a', required: false }),
      makeField({ id: '2', name: 'b', required: true }),
    ]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    const checkboxes = screen.getAllByRole('checkbox', { name: 'Required' })
    await user.click(checkboxes[0])
    const result = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(result[0].required).toBe(true)
    expect(result[1].required).toBe(true)
  })

  it('handles type change on second field in multi-field list', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const fields = [
      makeField({ id: '1', name: 'first', type: 'string' }),
      makeField({ id: '2', name: 'second', type: 'string' }),
    ]
    render(<SimpleSchemaBuilder fields={fields} onFieldsChange={onChange} />)

    const toggles = screen.getAllByRole('button', { name: 'String' })
    await user.click(toggles[1])
    await user.click(screen.getByRole('option', { name: 'Number' }))

    const result = onChange.mock.lastCall?.[0] as SimpleField[]
    expect(result[0].type).toBe('string')
    expect(result[1].type).toBe('number')
  })

  it('has no accessibility violations with empty fields', async () => {
    const { container } = render(<SimpleSchemaBuilder fields={[]} onFieldsChange={vi.fn()} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with populated fields', async () => {
    const fields = [
      makeField({ id: '1', name: 'event', type: 'string', required: true }),
      makeField({ id: '2', name: 'count', type: 'integer', required: false }),
    ]
    const { container } = render(<SimpleSchemaBuilder fields={fields} onFieldsChange={vi.fn()} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
