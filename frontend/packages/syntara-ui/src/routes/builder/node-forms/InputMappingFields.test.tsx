import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_FIELD } from '../../../components/expressions/expressionFieldDrag'

import { InputMappingFields } from './InputMappingFields'
import type { InvocationInputField } from './invocationSchemaUtils'

const schemaFields: InvocationInputField[] = [
  { name: 'host', type: 'string', required: true, description: 'Child target host' },
  { name: 'port', type: 'integer', required: false, defaultValue: 22 },
]
function StatefulMapping({
  fields = schemaFields,
  initialValues = {},
  isDisabled = false,
}: {
  fields?: InvocationInputField[]
  initialValues?: Record<string, unknown>
  isDisabled?: boolean
}) {
  const [values, setValues] = useState(initialValues)
  const [freeformJson, setFreeformJson] = useState('{}')

  return (
    <InputMappingFields
      fields={fields}
      values={values}
      onChange={setValues}
      freeformJson={freeformJson}
      onFreeformJsonChange={setFreeformJson}
      isDisabled={isDisabled}
    />
  )
}

describe('InputMappingFields', () => {
  it('renders a field for each declared child input and shows defaults', () => {
    render(<StatefulMapping />)

    expect(screen.getByRole('heading', { name: 'Input Mapping', level: 3 })).toBeInTheDocument()

    const hostField = screen.getByRole('textbox', { name: 'host' })
    const hostHint = screen.getByText('Child target host')

    expect(hostField).toBeRequired()
    expect(hostField).toHaveAccessibleDescription('Child target host')
    expect(hostHint.compareDocumentPosition(hostField) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0)
    expect(hostField).toHaveAttribute('placeholder', 'Enter or drag and drop value')
    expect(screen.getByRole('textbox', { name: 'port' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'port' })).toHaveAttribute('placeholder', 'Enter or drag and drop value')
    expect(screen.queryByRole('button', { name: /Insert variable/ })).not.toBeInTheDocument()
  })

  it('updates a child input value as the user types', async () => {
    const user = userEvent.setup()
    render(<StatefulMapping />)

    await user.type(screen.getByRole('textbox', { name: 'host' }), 'server.example')

    expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('server.example')
  })

  it('allows keyboard users to enter template expressions', async () => {
    const user = userEvent.setup()
    render(<StatefulMapping />)

    const hostInput = screen.getByRole('textbox', { name: 'host' })
    await user.click(hostInput)
    await user.paste('${lookup.hostname}')

    expect(hostInput).toHaveValue('${lookup.hostname}')
  })

  it('supports dragged expressions and type guidance for non-string child inputs', () => {
    const fields: InvocationInputField[] = [
      { name: 'retries', type: 'integer', required: false },
      { name: 'count', type: 'number', required: false },
      { name: 'enabled', type: 'boolean', required: false },
      { name: 'config', type: 'object', required: false },
      { name: 'tags', type: 'array', required: false },
    ]
    render(<StatefulMapping fields={fields} />)

    for (const field of fields) {
      const input = screen.getByRole('textbox', { name: field.name })
      expect(input).toHaveAttribute('placeholder', 'Enter or drag and drop value')

      fireEvent.drop(input, {
        dataTransfer: {
          getData: () =>
            JSON.stringify({
              type: DRAG_TYPE_FIELD,
              nodeId: 'parent-step',
              fieldPath: ['result', 'value'],
            }),
        },
      })

      expect(input).toHaveValue('${parent-step.result.value}')
    }
  })

  it('uses multiline expression fields for object and array inputs', () => {
    render(
      <StatefulMapping
        fields={[
          { name: 'config', type: 'object', required: true },
          { name: 'tags', type: 'array', required: false },
        ]}
      />
    )

    expect(screen.getByRole('textbox', { name: 'config' }).tagName).toBe('TEXTAREA')
    expect(screen.getByRole('textbox', { name: 'tags' }).tagName).toBe('TEXTAREA')
    expect(screen.getByRole('textbox', { name: 'config' })).toHaveAttribute(
      'placeholder',
      'Enter or drag and drop value'
    )
  })

  it('shows free-form JSON when the child schema declares no fields', () => {
    render(<StatefulMapping fields={[]} />)

    expect(screen.getByRole('textbox', { name: 'Input Mapping JSON' })).toHaveValue('{}')
    expect(screen.getByText('Enter a JSON object with child input values.')).toBeInTheDocument()
  })

  it('updates free-form JSON', async () => {
    const user = userEvent.setup()
    render(<StatefulMapping fields={[]} />)
    const mappingInput = screen.getByRole('textbox', { name: 'Input Mapping JSON' })

    await user.click(mappingInput)
    await user.clear(mappingInput)
    await user.paste('{"host":"server.example"}')

    expect(mappingInput).toHaveValue('{"host":"server.example"}')
  })

  it('disables inputs in version view', () => {
    render(<StatefulMapping isDisabled />)

    expect(screen.getByRole('textbox', { name: 'host' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'port' })).toBeDisabled()
  })

  it('shows form errors for invalid free-form JSON', () => {
    render(
      <InputMappingFields
        fields={[]}
        values={{}}
        onChange={vi.fn()}
        freeformJson="[]"
        onFreeformJsonChange={vi.fn()}
        error="Input mapping must be a JSON object."
      />
    )

    expect(screen.getByText('Input mapping must be a JSON object.')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<StatefulMapping />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
