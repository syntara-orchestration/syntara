import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'
import { expectStringContaining } from '../../../test/test-helpers'

import { RunWorkflowModal } from './RunWorkflowModal'

// Captures the latest onCodeChange so tests can set editor content directly,
// bypassing the controlled textarea (userEvent.type would append char-by-char
// and fight with React state on a mocked component).
let mockSetCode: ((v: string) => void) | undefined

vi.mock('./ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (v: string) => void
    ariaLabel?: string
    additionalControls?: React.ReactNode
  }) => {
    mockSetCode = onCodeChange
    return <textarea data-testid="mock-code-editor" aria-label={ariaLabel} value={code} readOnly />
  },
}))

vi.mock('./JsonEditorToolbar', () => ({
  JsonEditorControls: () => null,
}))

const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError, showSuccess: vi.fn() }),
}))

const mockUseQuery = vi.fn<(...args: unknown[]) => { data: unknown; isLoading: boolean }>()
vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]) => mockUseQuery(...args),
  },
}))

function renderModal(overrides: Partial<React.ComponentProps<typeof RunWorkflowModal>> = {}) {
  const props: React.ComponentProps<typeof RunWorkflowModal> = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    workflowName: 'my-workflow',
    triggerName: 'Manual Trigger',
    ...overrides,
  }
  return {
    ...render(
      <ColorSchemeProvider>
        <RunWorkflowModal {...props} />
      </ColorSchemeProvider>
    ),
    props,
  }
}

describe('RunWorkflowModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false })
  })

  it('does not render modal content when isOpen is false', () => {
    renderModal({ isOpen: false })
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
  })

  it('renders title with trigger name when open', () => {
    renderModal({ triggerName: 'My Trigger' })
    expect(screen.getByText('Set mock output data for My Trigger')).toBeInTheDocument()
  })

  it('renders Run and Cancel buttons', () => {
    renderModal()
    expect(screen.getByRole('button', { name: 'Run' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const { props } = renderModal()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onConfirm with parsed JSON when Run is clicked with valid JSON', async () => {
    const user = userEvent.setup()
    const { props } = renderModal()

    act(() => mockSetCode?.('{"host": "server1"}'))
    await user.click(screen.getByRole('button', { name: 'Run' }))

    expect(props.onConfirm).toHaveBeenCalledWith({ host: 'server1' }, undefined)
  })

  it('passes triggerNodeId to onConfirm when provided', async () => {
    const user = userEvent.setup()
    const { props } = renderModal({ triggerNodeId: 'trigger-abc-123' })

    await user.click(screen.getByRole('button', { name: 'Run' }))

    expect(props.onConfirm).toHaveBeenCalledWith({}, 'trigger-abc-123')
  })

  it('shows error when Run is clicked with invalid JSON', async () => {
    const user = userEvent.setup()
    const { props } = renderModal()

    act(() => mockSetCode?.('not valid json'))
    await user.click(screen.getByRole('button', { name: 'Run' }))

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Invalid JSON',
      description: 'The data must be valid JSON.',
    })
    expect(props.onConfirm).not.toHaveBeenCalled()
  })

  describe('template generation', () => {
    it('generates template from inputSchema properties', () => {
      const inputSchema = {
        type: 'object',
        properties: {
          name: { type: 'string' },
          count: { type: 'number' },
          active: { type: 'boolean' },
        },
      }
      renderModal({ inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      const parsed = JSON.parse(editor.value) as Record<string, unknown>
      expect(parsed).toEqual({ name: '', count: 0, active: false })
    })

    it('uses default values from schema when present', () => {
      const inputSchema = {
        type: 'object',
        properties: {
          env: { type: 'string', default: 'production' },
        },
      }
      renderModal({ inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      const parsed = JSON.parse(editor.value) as Record<string, unknown>
      expect(parsed).toEqual({ env: 'production' })
    })

    it('starts with empty object when no inputSchema', () => {
      renderModal()
      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      expect(editor.value).toBe('{}')
    })
  })

  describe('schema validation', () => {
    const schema = {
      type: 'object',
      properties: {
        name: { type: 'string' },
        count: { type: 'number' },
      },
      required: ['name'],
    }

    it('rejects when required field is missing', async () => {
      const user = userEvent.setup()
      const { props } = renderModal({ inputSchema: schema })

      act(() => mockSetCode?.('{"count": 5}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Missing required field: "name"'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('rejects when field type does not match schema', async () => {
      const user = userEvent.setup()
      const { props } = renderModal({ inputSchema: schema })

      act(() => mockSetCode?.('{"name": 123}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Field "name" should be string'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('accepts valid data matching schema', async () => {
      const user = userEvent.setup()
      const { props } = renderModal({ inputSchema: schema })

      act(() => mockSetCode?.('{"name": "test", "count": 5}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ name: 'test', count: 5 }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('accepts integer-typed field with a number value', async () => {
      const user = userEvent.setup()
      const intSchema = {
        type: 'object',
        properties: { qty: { type: 'integer' } },
        required: ['qty'],
      }
      const { props } = renderModal({ inputSchema: intSchema })

      act(() => mockSetCode?.('{"qty": 42}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ qty: 42 }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('rejects when integer-typed field receives a string', async () => {
      const user = userEvent.setup()
      const intSchema = {
        type: 'object',
        properties: { qty: { type: 'integer' } },
        required: ['qty'],
      }
      const { props } = renderModal({ inputSchema: intSchema })

      act(() => mockSetCode?.('{"qty": "not-a-number"}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Field "qty" should be integer'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('accepts boolean-typed field with a boolean value', async () => {
      const user = userEvent.setup()
      const boolSchema = {
        type: 'object',
        properties: { enabled: { type: 'boolean' } },
        required: ['enabled'],
      }
      const { props } = renderModal({ inputSchema: boolSchema })

      act(() => mockSetCode?.('{"enabled": true}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ enabled: true }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('rejects when boolean-typed field receives a string', async () => {
      const user = userEvent.setup()
      const boolSchema = {
        type: 'object',
        properties: { enabled: { type: 'boolean' } },
        required: ['enabled'],
      }
      const { props } = renderModal({ inputSchema: boolSchema })

      act(() => mockSetCode?.('{"enabled": "yes"}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Field "enabled" should be boolean'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('accepts array-typed field with an array value', async () => {
      const user = userEvent.setup()
      const arraySchema = {
        type: 'object',
        properties: { tags: { type: 'array' } },
        required: ['tags'],
      }
      const { props } = renderModal({ inputSchema: arraySchema })

      act(() => mockSetCode?.('{"tags": ["a", "b"]}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ tags: ['a', 'b'] }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('rejects when array-typed field receives an object', async () => {
      const user = userEvent.setup()
      const arraySchema = {
        type: 'object',
        properties: { tags: { type: 'array' } },
        required: ['tags'],
      }
      const { props } = renderModal({ inputSchema: arraySchema })

      act(() => mockSetCode?.('{"tags": {"a": 1}}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Field "tags" should be array'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('accepts object-typed field with a plain object value', async () => {
      const user = userEvent.setup()
      const objSchema = {
        type: 'object',
        properties: { parameters: { type: 'object' } },
        required: ['parameters'],
      }
      const { props } = renderModal({ inputSchema: objSchema })

      act(() => mockSetCode?.('{"parameters": {"key": "value"}}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ parameters: { key: 'value' } }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('rejects when object-typed field receives an array', async () => {
      const user = userEvent.setup()
      const objSchema = {
        type: 'object',
        properties: { parameters: { type: 'object' } },
        required: ['parameters'],
      }
      const { props } = renderModal({ inputSchema: objSchema })

      act(() => mockSetCode?.('{"parameters": [1, 2]}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Validation failed',
        description: expectStringContaining('Field "parameters" should be object'),
      })
      expect(props.onConfirm).not.toHaveBeenCalled()
    })

    it('accepts any value when property has no type defined (default permissive)', async () => {
      const user = userEvent.setup()
      const noTypeSchema = {
        type: 'object',
        properties: { anything: {} },
        required: ['anything'],
      }
      const { props } = renderModal({ inputSchema: noTypeSchema })

      act(() => mockSetCode?.('{"anything": 42}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ anything: 42 }, undefined)
      expect(mockShowError).not.toHaveBeenCalled()
    })
  })

  describe('template generation for additional types', () => {
    it('generates integer and boolean template values from schema', () => {
      const inputSchema = {
        type: 'object',
        properties: {
          count: { type: 'integer' },
          enabled: { type: 'boolean' },
          tags: { type: 'array' },
          parameters: { type: 'object' },
          extra: {},
        },
      }
      renderModal({ inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      const parsed = JSON.parse(editor.value) as Record<string, unknown>
      expect(parsed.count).toBe(0)
      expect(parsed.enabled).toBe(false)
      expect(parsed.tags).toEqual([])
      expect(parsed.parameters).toEqual({})
      expect(parsed.extra).toBeNull()
    })

    it('falls back to raw schema value when schema type is not object', () => {
      const inputSchema = { type: 'array', items: { type: 'string' } }
      renderModal({ inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      expect(editor.value).toBe(JSON.stringify(inputSchema, null, 2))
    })

    it('falls back to raw data when input is not a JSON Schema', () => {
      const inputSchema = { host: 'web-prod-04.example.com', severity: 'critical' }
      renderModal({ inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      expect(editor.value).toBe(JSON.stringify(inputSchema, null, 2))
    })
  })

  function mockPreviousRunData(triggerNodeId: string, outputData: Record<string, unknown>) {
    mockUseQuery.mockImplementation((_method: unknown, path: unknown) => {
      if (path === '/executions') {
        return {
          data: { resources: [{ id: 'exec-123', status: 'completed' }] },
          isLoading: false,
        }
      }
      if (path === '/executions/{execution_id}/activities') {
        return {
          data: {
            resources: [{ activity_name: triggerNodeId, output_data: outputData }],
          },
          isLoading: false,
        }
      }
      return { data: undefined, isLoading: false }
    })
  }

  describe('pre-population from previous run', () => {
    it('pre-populates editor with data from the latest successful run', () => {
      const previousData = { host: 'server1', port: 8080 }
      mockPreviousRunData('trigger-1', previousData)

      renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1' })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      expect(JSON.parse(editor.value)).toEqual(previousData)
    })

    it('shows helper text when pre-populated', () => {
      mockPreviousRunData('trigger-1', { host: 'server1' })

      renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1' })

      expect(screen.getByText('Pre-populated from the last successful run')).toBeInTheDocument()
    })

    it('falls back to schema template when no previous run exists', () => {
      const inputSchema = {
        type: 'object',
        properties: { name: { type: 'string' } },
      }
      renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1', inputSchema })

      const editor: HTMLTextAreaElement = screen.getByRole('textbox', { name: /workflow data editor/i })
      expect(JSON.parse(editor.value)).toEqual({ name: '' })
      expect(screen.queryByText('Pre-populated from the last successful run')).not.toBeInTheDocument()
    })

    it('does not show helper text after user edits the code', () => {
      mockPreviousRunData('trigger-1', { host: 'server1' })

      renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1' })

      act(() => mockSetCode?.('{"host": "custom-host"}'))

      expect(screen.queryByText('Pre-populated from the last successful run')).not.toBeInTheDocument()
    })

    it('submits user-edited data, not original pre-populated data', async () => {
      const user = userEvent.setup()
      mockPreviousRunData('trigger-1', { host: 'server1' })

      const { props } = renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1' })

      act(() => mockSetCode?.('{"host": "custom-host"}'))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      expect(props.onConfirm).toHaveBeenCalledWith({ host: 'custom-host' }, 'trigger-1')
    })

    it('does not fetch when workflowId is not provided', () => {
      renderModal({ triggerNodeId: 'trigger-1' })

      const execCall = mockUseQuery.mock.calls.find((call) => call[1] === '/executions')
      if (execCall) {
        expect(execCall[3]).toEqual(expect.objectContaining({ enabled: false }))
      }
    })
  })

  describe('accessibility', () => {
    it('has no violations when open', async () => {
      const { container } = renderModal()
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no violations when pre-populated', async () => {
      mockPreviousRunData('trigger-1', { host: 'server1' })
      const { container } = renderModal({ workflowId: 'wf-abc', triggerNodeId: 'trigger-1' })
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
