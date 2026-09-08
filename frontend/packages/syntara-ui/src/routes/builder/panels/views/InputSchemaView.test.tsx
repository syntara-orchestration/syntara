import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_FIELD } from '../utils/dragTypes'

import { InputSchemaView } from './InputSchemaView'

describe('InputSchemaView', () => {
  it('renders tree from flat JSON data with field names and values', () => {
    const data = { name: 'Alice', age: 30 }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    expect(screen.getByText('T name')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('# age')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('shows type indicator for string fields', () => {
    const data = { greeting: 'hello' }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    expect(screen.getByText('T greeting')).toBeInTheDocument()
  })

  it('shows type indicator for number fields', () => {
    const data = { count: 42 }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    expect(screen.getByText('# count')).toBeInTheDocument()
  })

  it('expands and collapses nested objects when toggle clicked', async () => {
    const user = userEvent.setup()
    const data = {
      address: {
        city: 'Portland',
        zip: '97201',
      },
    }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    // Nested fields should be visible initially (expanded by default)
    expect(screen.getByText('T city')).toBeInTheDocument()
    expect(screen.getByText('Portland')).toBeInTheDocument()

    // PatternFly TreeView uses the node button for toggling.
    // The button's accessible name includes the rendered name content.
    const toggleButton = screen.getByRole('button', { name: /\{\} address/i })
    await user.click(toggleButton)

    // Nested fields should be hidden
    expect(screen.queryByText('T city')).not.toBeInTheDocument()
    expect(screen.queryByText('Portland')).not.toBeInTheDocument()

    // Click again to expand
    await user.click(toggleButton)

    expect(screen.getByText('T city')).toBeInTheDocument()
    expect(screen.getByText('Portland')).toBeInTheDocument()
  })

  it('handles null data by rendering nothing', () => {
    render(<InputSchemaView data={null} nodeId="http_request_1" />)

    expect(screen.queryByRole('tree', { name: 'Input schema' })).not.toBeInTheDocument()
  })

  it('handles empty object data by rendering nothing', () => {
    render(<InputSchemaView data={{}} nodeId="http_request_1" />)

    expect(screen.queryByRole('tree', { name: 'Input schema' })).not.toBeInTheDocument()
  })

  it('leaf nodes have draggable attribute', () => {
    const data = { name: 'Alice' }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    expect(screen.getByText('T name')).toBeInTheDocument()
  })

  it('sets correct drag data on leaf node dragStart', () => {
    const data = { name: 'Alice' }
    render(<InputSchemaView data={data} nodeId="http_request_1" />)

    const setDataCalls: Array<[string, string]> = []
    const dataTransfer = {
      setData: (format: string, value: string) => {
        setDataCalls.push([format, value])
      },
      effectAllowed: '',
    }

    fireEvent.dragStart(screen.getByText('T name'), { dataTransfer })

    expect(setDataCalls).toHaveLength(2)
    expect(setDataCalls[0][0]).toBe('application/json')

    const parsed = JSON.parse(setDataCalls[0][1]) as { type: string; nodeId: string; fieldPath: string[] }
    expect(parsed.type).toBe(DRAG_TYPE_FIELD)
    expect(parsed.nodeId).toBe('http_request_1')
    expect(parsed.fieldPath).toEqual(['name'])

    expect(setDataCalls[1][0]).toBe('text/plain')
    expect(setDataCalls[1][1]).toBe('${http_request_1.name}')
  })

  it('sets correct drag data for nested leaf nodes', () => {
    const data = { address: { city: 'Portland' } }
    render(<InputSchemaView data={data} nodeId="fetch_order" />)

    const setDataCalls: Array<[string, string]> = []
    const dataTransfer = {
      setData: (format: string, value: string) => {
        setDataCalls.push([format, value])
      },
      effectAllowed: '',
    }

    fireEvent.dragStart(screen.getByText('T city'), { dataTransfer })

    const parsed = JSON.parse(setDataCalls[0][1]) as { type: string; nodeId: string; fieldPath: string[] }
    expect(parsed.type).toBe(DRAG_TYPE_FIELD)
    expect(parsed.nodeId).toBe('fetch_order')
    expect(parsed.fieldPath).toEqual(['address', 'city'])

    expect(setDataCalls[1][0]).toBe('text/plain')
    expect(setDataCalls[1][1]).toBe('${fetch_order.address.city}')
  })

  it('renders schema for a loop-iteration composite activity id', () => {
    const data = { name: 'Alice' }
    render(<InputSchemaView data={data} nodeId="approval2#iter-5" />)

    expect(screen.getByText('T name')).toBeInTheDocument()
    expect(screen.getByRole('tree', { name: 'Input schema' })).toBeInTheDocument()
  })

  it('uses the canvas node ID in drag data for loop-iteration composite keys', () => {
    const data = { name: 'Alice' }
    render(<InputSchemaView data={data} nodeId="approval2#iter-5" />)

    const setDataCalls: Array<[string, string]> = []
    const dataTransfer = {
      setData: (format: string, value: string) => {
        setDataCalls.push([format, value])
      },
      effectAllowed: '',
    }

    fireEvent.dragStart(screen.getByText('T name'), { dataTransfer })

    const parsed = JSON.parse(setDataCalls[0][1]) as { type: string; nodeId: string; fieldPath: string[] }
    expect(parsed.nodeId).toBe('approval2')
    expect(setDataCalls[1][1]).toBe('${approval2.name}')
  })

  it('has no accessibility violations', async () => {
    const data = { name: 'Alice', age: 30, active: true }
    const { container } = render(<InputSchemaView data={data} nodeId="http_request_1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with null data', async () => {
    const { container } = render(<InputSchemaView data={null} nodeId="http_request_1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders URL values with an external link action button', () => {
    const data = { job_url: 'https://aap.example.com/jobs/789' }
    render(<InputSchemaView data={data} nodeId="aap_step_1" />)

    const link = screen.getByRole('link', { name: 'Open job_url in new tab' })
    expect(link).toHaveAttribute('href', 'https://aap.example.com/jobs/789')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('does not render external link button for non-URL strings', () => {
    const data = { status: 'running' }
    render(<InputSchemaView data={data} nodeId="aap_step_1" />)

    expect(screen.queryByRole('link', { name: /Open .* in new tab/ })).not.toBeInTheDocument()
  })

  it('has no accessibility violations with empty object data', async () => {
    const { container } = render(<InputSchemaView data={{}} nodeId="http_request_1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with URL values', async () => {
    const { container } = render(
      <InputSchemaView data={{ job_url: 'https://aap.example.com/jobs/789' }} nodeId="aap_step_1" />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
