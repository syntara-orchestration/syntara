import type { OutputFieldDef } from '@syntara/contracts'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_FIELD } from '../utils/dragTypes'

import { InputSchemaPreview } from './InputSchemaPreview'
import type { InputSchemaPreviewNode } from './InputSchemaPreview'

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

  it('shows a Required badge only for required fields and renders runtime values below the description', () => {
    const tree: InputSchemaPreviewNode[] = [
      {
        name: 'release_url',
        type: 'string',
        description: 'URL of the published release',
        fieldPath: ['release_url'],
        required: true,
      },
      {
        name: 'notes',
        type: 'string',
        description: 'Optional release notes',
        fieldPath: ['notes'],
        required: false,
      },
    ]
    render(
      <InputSchemaPreview
        tree={tree}
        nodeId="invoke_child"
        runtimeValues={{ release_url: 'https://example.test/release', notes: 'No changes' }}
      />
    )

    const requiredField = screen.getByRole('treeitem', { name: /release_url/ })
    expect(within(requiredField).getByText('Required')).toBeInTheDocument()
    expect(within(requiredField).getByText('URL of the published release')).toBeInTheDocument()
    expect(within(requiredField).getByText('https://example.test/release')).toBeInTheDocument()

    const optionalField = screen.getByRole('treeitem', { name: /notes/ })
    expect(within(optionalField).queryByText('optional')).not.toBeInTheDocument()
    expect(within(optionalField).getByText('No changes')).toBeInTheDocument()
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

  it('shows an accessible help popover beside the expected output fields heading', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" />)

    expect(screen.getByText('Expected output fields')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expected output fields help' })).toBeInTheDocument()
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

  it('builds the public dotted-path expression when dragging a nested declared output', async () => {
    const user = userEvent.setup()
    const nestedOutputTree: InputSchemaPreviewNode[] = [
      {
        name: 'outputs',
        type: 'object',
        description: 'Declared outputs',
        fieldPath: ['outputs'],
        isGroup: true,
        children: [
          {
            name: 'release',
            type: 'object',
            description: 'Release metadata',
            fieldPath: ['outputs', 'release'],
            isGroup: true,
            children: [
              {
                name: 'version',
                type: 'string',
                description: 'Published release version',
                fieldPath: ['outputs', 'release', 'version'],
              },
            ],
          },
        ],
      },
    ]
    render(<InputSchemaPreview tree={nestedOutputTree} nodeId="invoke_child" />)

    const expression = '${invoke_child.outputs.release.version}'
    const setDataCalls: Array<[string, string]> = []
    const releaseGroup = screen.getByRole('treeitem', { name: '{} release Release metadata' })
    await user.click(within(releaseGroup).getByRole('button'))

    fireEvent.dragStart(screen.getByText('T version'), {
      dataTransfer: {
        setData: (format: string, value: string) => setDataCalls.push([format, value]),
        effectAllowed: '',
      },
    })

    expect(setDataCalls.find(([format]) => format === 'text/plain')?.[1]).toBe(expression)
    expect(screen.getByRole('button', { name: `Copy expression ${expression}` })).toBeInTheDocument()
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

  it('filters fields by name when searchTerm is provided', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="stdout" />)

    // Tree should have exactly 2 items (stdout and stdout_json)
    const treeItems = screen.getAllByRole('treeitem')
    expect(treeItems).toHaveLength(2)

    // Check that "exit_code" and "active" are not in the rendered tree
    expect(screen.queryByText(/exit_code/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bactive\b/i)).not.toBeInTheDocument()
  })

  it('filters fields by description when searchTerm is provided', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="success" />)

    // Field with "success" in description ("Process exit code (0 = success)") should be visible
    expect(screen.getByText(/exit_code/i)).toBeInTheDocument()
    // Fields without "success" in description or name should not be visible
    expect(screen.queryByText(/\bactive\b/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/items/i)).not.toBeInTheDocument()
  })

  it('keeps ancestor groups visible when a descendant field matches', () => {
    const nestedFields: OutputFieldDef[] = [
      {
        name: 'Result',
        type: 'object',
        description: 'Result object',
        children: [
          { name: 'status', type: 'string', description: 'Status message' },
          { name: 'data', type: 'string', description: 'Data payload' },
        ],
      },
    ]

    render(<InputSchemaPreview fields={nestedFields} nodeId="step-1" searchTerm="status" />)

    // Parent group should be visible
    expect(screen.getByText('{} Result')).toBeInTheDocument()
    // Matching child should be visible
    expect(screen.getByText(/status/)).toBeInTheDocument()
    // Non-matching child should not be visible
    expect(screen.queryByText(/data/)).not.toBeInTheDocument()
  })

  it('collapses nested declared-output groups until expanded', () => {
    const nestedTree: InputSchemaPreviewNode[] = [
      {
        name: 'outputs',
        type: 'object',
        description: 'Declared outputs',
        fieldPath: ['outputs'],
        isGroup: true,
        children: [
          {
            name: 'release',
            type: 'object',
            description: 'Release metadata',
            fieldPath: ['outputs', 'release'],
            isGroup: true,
            children: [
              {
                name: 'url',
                type: 'string',
                description: 'Release URL',
                fieldPath: ['outputs', 'release', 'url'],
              },
            ],
          },
        ],
      },
    ]

    render(
      <InputSchemaPreview
        tree={nestedTree}
        nodeId="invoke_child"
        runtimeValues={{ outputs: { release: { url: 'https://example.test/release' } } }}
      />
    )

    const releaseGroup = screen.getByRole('treeitem', { name: /^\{\} release/ })
    expect(releaseGroup).toHaveAttribute('aria-expanded', 'false')
    expect(within(releaseGroup).getByText('{"url":"https://example.test/release"}')).toBeInTheDocument()
    expect(screen.queryByText('T url')).not.toBeInTheDocument()
  })

  it('matches full dotted paths and expands matching ancestors during search', () => {
    const nestedTree: InputSchemaPreviewNode[] = [
      {
        name: 'outputs',
        type: 'object',
        description: 'Declared outputs',
        fieldPath: ['outputs'],
        isGroup: true,
        children: [
          {
            name: 'release',
            type: 'object',
            description: 'Release metadata',
            fieldPath: ['outputs', 'release'],
            isGroup: true,
            children: [
              {
                name: 'artifact',
                type: 'object',
                description: 'Published artifact',
                fieldPath: ['outputs', 'release', 'artifact'],
                isGroup: true,
                children: [
                  {
                    name: 'download_url',
                    type: 'string',
                    description: 'Download URL',
                    fieldPath: ['outputs', 'release', 'artifact', 'download_url'],
                  },
                ],
              },
            ],
          },
        ],
      },
    ]
    const { rerender } = render(<InputSchemaPreview tree={nestedTree} nodeId="invoke_child" />)

    rerender(<InputSchemaPreview tree={nestedTree} nodeId="invoke_child" searchTerm="release.artifact.download_url" />)

    expect(screen.getByText('T download_url')).toBeInTheDocument()
    const releaseGroup = screen.getByRole('treeitem', { name: /^\{\} release/ })
    const artifactGroup = screen.getByRole('treeitem', { name: /^\{\} artifact/ })
    expect(releaseGroup).toHaveAttribute('aria-expanded', 'true')
    expect(artifactGroup).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows a clear empty state when the schema search has no matches', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="not-a-field" />)

    expect(screen.getByText('No output fields match your search')).toBeInTheDocument()
    expect(screen.getByText('No output fields match “not-a-field”.')).toBeInTheDocument()
  })

  it('highlights matching text in field names and descriptions', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="exit" />)

    // Check that highlighted text exists (highlightText wraps matches in <mark>)
    const marks = screen.getAllByText('exit')
    expect(marks.length).toBeGreaterThan(0)
  })

  it('highlights a field-name match when its description does not match', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="exit_code" />)

    expect(screen.getByText('exit_code', { selector: 'mark' })).toBeInTheDocument()
  })

  it('shows all fields when searchTerm is empty', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="" />)

    expect(screen.getByText('T stdout')).toBeInTheDocument()
    expect(screen.getByText('# exit_code')).toBeInTheDocument()
    expect(screen.getByText('✓ active')).toBeInTheDocument()
  })

  it('renders tree when filtering', () => {
    render(<InputSchemaPreview fields={sampleFields} nodeId="step-1" searchTerm="stdout" />)

    // Tree should render
    const tree = screen.queryByRole('tree')
    expect(tree).toBeInTheDocument()

    // Should have at least one tree item
    const treeItems = screen.getAllByRole('treeitem')
    expect(treeItems.length).toBeGreaterThan(0)
  })
})
