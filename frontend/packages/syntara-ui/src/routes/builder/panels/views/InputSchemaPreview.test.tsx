import type { OutputFieldDef } from '@syntara/contracts'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_FIELD } from '../utils/dragTypes'
import type { PreviewFieldDef } from '../utils/effectiveOutputSchema'

import { InputSchemaPreview } from './InputSchemaPreview'

const sampleFields: OutputFieldDef[] = [
  { name: 'stdout', type: 'string', description: 'Standard output from the script execution' },
  { name: 'exit_code', type: 'number', description: 'Process exit code (0 = success)' },
  { name: 'active', type: 'boolean', description: 'Whether the process is active' },
  { name: 'stdout_json', type: 'object', description: 'Parsed JSON from stdout' },
  { name: 'items', type: 'array', description: 'List of results' },
]

describe('InputSchemaPreview', () => {
  it('renders all field names with type indicators', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    expect(screen.getByText('T stdout')).toBeInTheDocument()
    expect(screen.getByText('# exit_code')).toBeInTheDocument()
    expect(screen.getByText('\u2713 active')).toBeInTheDocument()
    expect(screen.getByText('{} stdout_json')).toBeInTheDocument()
    expect(screen.getByText('[] items')).toBeInTheDocument()
  })

  it('renders field descriptions', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    expect(screen.getByText('Standard output from the script execution')).toBeInTheDocument()
    expect(screen.getByText('Process exit code (0 = success)')).toBeInTheDocument()
  })

  it('renders type label T for string fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'message', type: 'string', description: 'A text field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('T message')).toBeInTheDocument()
  })

  it('renders type label # for number fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'count', type: 'number', description: 'A numeric field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('# count')).toBeInTheDocument()
  })

  it('renders type label checkmark for boolean fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'enabled', type: 'boolean', description: 'A boolean field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('\u2713 enabled')).toBeInTheDocument()
  })

  it('renders type label {} for object fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'data', type: 'object', description: 'An object field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('{} data')).toBeInTheDocument()
  })

  it('renders type label [] for array fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'list', type: 'array', description: 'An array field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('[] list')).toBeInTheDocument()
  })

  it('renders type label ? for unknown fields', () => {
    const fields: OutputFieldDef[] = [{ name: 'mystery', type: 'unknown', description: 'An unknown field' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('? mystery')).toBeInTheDocument()
  })

  it('renders the info banner about expected output fields', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    expect(screen.getByText('Expected output fields (run step to see actual values)')).toBeInTheDocument()
  })

  it('renders a tree with the schema preview aria-label', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    expect(screen.getByRole('tree', { name: 'Schema preview' })).toBeInTheDocument()
  })

  it('fields have draggable attribute', () => {
    const fields: OutputFieldDef[] = [{ name: 'hostname', type: 'string', description: 'The hostname' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    expect(screen.getByText('T hostname')).toBeInTheDocument()
  })

  it('sets correct drag data on field dragStart', () => {
    const fields: OutputFieldDef[] = [{ name: 'hostname', type: 'string', description: 'The hostname' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1" />)

    const setDataCalls: Array<[string, string]> = []
    const dataTransfer = {
      setData: (format: string, value: string) => {
        setDataCalls.push([format, value])
      },
      effectAllowed: '',
    }

    fireEvent.dragStart(screen.getByText('T hostname'), { dataTransfer })

    expect(setDataCalls).toHaveLength(2)
    expect(setDataCalls[0][0]).toBe('application/json')

    const parsed = JSON.parse(setDataCalls[0][1]) as { type: string; nodeId: string; fieldPath: string[] }
    expect(parsed.type).toBe(DRAG_TYPE_FIELD)
    expect(parsed.nodeId).toBe('step-1')
    expect(parsed.fieldPath).toEqual(['hostname'])

    expect(setDataCalls[1][0]).toBe('text/plain')
    expect(setDataCalls[1][1]).toBe('${step-1.hostname}')
  })

  it('renders schema preview for a loop-iteration composite activity id', () => {
    const fields: OutputFieldDef[] = [{ name: 'hostname', type: 'string', description: 'The hostname' }]
    render(<InputSchemaPreview fields={fields} nodeId="step-1#iter-2" />)

    expect(screen.getByText('T hostname')).toBeInTheDocument()
    expect(screen.getByRole('tree', { name: 'Schema preview' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders nothing when fields array is empty', () => {
    const { container } = render(<InputSchemaPreview fields={[]} nodeId="step-1" />)

    expect(container.innerHTML).toBe('')
  })
})

describe('InputSchemaPreview nested fields', () => {
  const formFields: PreviewFieldDef[] = [
    { name: 'status', type: 'string', description: 'Form was submitted or timed out' },
    {
      name: 'response_data',
      type: 'object',
      description: 'Submitted form field values',
      children: [
        { name: 'email', type: 'string', description: 'Work address', displayName: 'Email address' },
        { name: 'age', type: 'number', description: '', displayName: 'age' },
      ],
    },
  ]

  function captureDrag(element: HTMLElement) {
    const calls: Array<[string, string]> = []
    const dataTransfer = {
      setData: (format: string, value: string) => {
        calls.push([format, value])
      },
      effectAllowed: '',
    }
    fireEvent.dragStart(element, { dataTransfer })
    return Object.fromEntries(calls)
  }

  it('shows nested children expanded by default without user interaction', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    expect(screen.getByText('{} response_data')).toBeInTheDocument()
    expect(screen.getByText('T email')).toBeInTheDocument()
    expect(screen.getByText('# age')).toBeInTheDocument()
  })

  it('combines a differing display name with the description as secondary text', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    expect(screen.getByText('Email address — Work address')).toBeInTheDocument()
  })

  it('omits secondary text when the display name matches the name and there is no description', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    expect(screen.queryByText('age')).not.toBeInTheDocument()
  })

  it('carries the full nested path in the drag payload and plain-text expression', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    const data = captureDrag(screen.getByText('T email'))

    expect(JSON.parse(data['application/json'])).toStrictEqual({
      type: DRAG_TYPE_FIELD,
      nodeId: 'prompt-1',
      fieldPath: ['response_data', 'email'],
    })
    expect(data['text/plain']).toBe('${prompt-1.response_data.email}')
  })

  it('keeps the top-level path for the parent field', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    const data = captureDrag(screen.getByText('{} response_data'))

    expect(JSON.parse(data['application/json'])).toMatchObject({ fieldPath: ['response_data'] })
    expect(data['text/plain']).toBe('${prompt-1.response_data}')
  })

  it('offers an accessible copy button for each nested path', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    expect(screen.getByRole('button', { name: 'Copy expression ${prompt-1.response_data}' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy expression ${prompt-1.response_data.email}' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy expression ${prompt-1.response_data.age}' })).toBeInTheDocument()
  })

  it('copies the complete nested expression to the clipboard', async () => {
    const user = userEvent.setup()
    render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    await user.click(screen.getByRole('button', { name: 'Copy expression ${prompt-1.response_data.email}' }))

    expect(await navigator.clipboard.readText()).toBe('${prompt-1.response_data.email}')
  })

  it('uses the trigger namespace for form trigger fields', () => {
    render(<InputSchemaPreview fields={formFields} nodeId="trigger" />)

    expect(screen.getByRole('button', { name: 'Copy expression ${trigger.response_data.email}' })).toBeInTheDocument()
  })

  it('renders sibling and nested fields that share a name as separate items', () => {
    const fields: PreviewFieldDef[] = [
      { name: 'email', type: 'string', description: 'Top-level' },
      {
        name: 'response_data',
        type: 'object',
        description: '',
        children: [{ name: 'email', type: 'string', description: '' }],
      },
    ]
    render(<InputSchemaPreview fields={fields} nodeId="prompt-1" />)

    expect(screen.getAllByText('T email')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Copy expression ${prompt-1.email}' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy expression ${prompt-1.response_data.email}' })).toBeInTheDocument()
  })

  it('does not nest anything for a field with an empty children array', () => {
    const fields: PreviewFieldDef[] = [{ name: 'response_data', type: 'object', description: '', children: [] }]
    render(<InputSchemaPreview fields={fields} nodeId="prompt-1" />)

    expect(screen.getAllByRole('treeitem')).toHaveLength(1)
  })

  it('has no accessibility violations with nested fields', async () => {
    const { container } = render(<InputSchemaPreview fields={formFields} nodeId="prompt-1" />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
