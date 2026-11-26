import { ActivityTypeEnum } from '@syntara/contracts'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ChildWorkflowSchemaFetchError } from '../childWorkflowSchemaApi'

import { useChildWorkflowSchema } from './hooks/useChildWorkflowSchema'
import type { ChildWorkflowStepSchema } from './hooks/useChildWorkflowSchema'
import type { UpstreamNodeInfo } from './hooks/useUpstreamNodes'
import { InputNodeContent } from './InputNodeContent'

vi.mock('./hooks/useChildWorkflowSchema', () => ({ useChildWorkflowSchema: vi.fn() }))

const upstreamNode: UpstreamNodeInfo = {
  id: 'invoke_child',
  name: 'Call child',
  type: ActivityTypeEnum.SUB_WORKFLOW,
  childWorkflowId: 'child-workflow',
  childTriggerNodeId: 'child-entry',
}

type ChildWorkflowSchemaState = ReturnType<typeof useChildWorkflowSchema>

function makeSchemaState(overrides: Partial<ChildWorkflowSchemaState> = {}): ChildWorkflowSchemaState {
  return {
    invocationSchema: null,
    publishedVersionId: null,
    publishedVersion: null,
    selectedTriggerNodeId: null,
    needsTriggerSelection: false,
    isTriggerUnavailable: false,
    childSteps: [],
    isLoading: false,
    error: null,
    isAccessDenied: false,
    isNotFound: false,
    isEligible: false,
    retry: vi.fn(),
    ...overrides,
  }
}

function renderInputNodeContent() {
  return render(
    <InputNodeContent
      upstreamNode={upstreamNode}
      hasData={false}
      mergedExecutionData={null}
      triggers={undefined}
      activeView="schema"
      searchTerm=""
    />
  )
}

function declaredOutputs(): ChildWorkflowStepSchema {
  return {
    id: '__declared_outputs__',
    name: 'Declared Outputs',
    type: 'subworkflow_declared_outputs',
    outputSchema: { type: 'object', properties: { status: { type: 'string' } } },
    outputFields: [{ name: 'status', type: 'string', description: 'Public status' }],
  }
}

describe('InputNodeContent for Sub-workflow steps', () => {
  beforeEach(() => {
    vi.mocked(useChildWorkflowSchema).mockReturnValue(makeSchemaState())
  })

  it('requests schema for the configured child workflow and trigger', () => {
    renderInputNodeContent()

    expect(useChildWorkflowSchema).toHaveBeenCalledWith({
      workflowId: 'child-workflow',
      triggerNodeId: 'child-entry',
    })
  })

  it('shows a loading state and aggregate fields while child metadata loads', () => {
    vi.mocked(useChildWorkflowSchema).mockReturnValue(makeSchemaState({ isLoading: true }))

    renderInputNodeContent()

    expect(screen.getByLabelText('Loading child workflow outputs')).toBeInTheDocument()
    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.queryByText('T stdout')).not.toBeInTheDocument()
  })

  it('shows hierarchical child outputs after a successful lookup', async () => {
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        selectedTriggerNodeId: 'child-entry',
        isEligible: true,
        childSteps: [declaredOutputs()],
      })
    )

    const { container } = renderInputNodeContent()

    // Aggregate fields should be visible
    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.getByRole('tree', { name: 'Schema preview' })).toBeInTheDocument()

    // Only declared public outputs are listed; internal step names stay hidden.
    expect(screen.getByText('T status')).toBeInTheDocument()
    expect(screen.queryByText('{} Deploy application')).not.toBeInTheDocument()

    const dragCalls: Array<[string, string]> = []
    fireEvent.dragStart(screen.getByText('T status'), {
      dataTransfer: {
        setData: (format: string, value: string) => dragCalls.push([format, value]),
        effectAllowed: '',
      },
    })
    expect(dragCalls.find(([format]) => format === 'text/plain')?.[1]).toBe('${invoke_child.outputs.status}')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows schema descriptions and runtime values together for a completed child', async () => {
    const user = userEvent.setup()
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        selectedTriggerNodeId: 'child-entry',
        isEligible: true,
        childSteps: [declaredOutputs()],
      })
    )

    render(
      <InputNodeContent
        upstreamNode={upstreamNode}
        hasData
        mergedExecutionData={{
          invoke_child: {
            child_execution_id: 'execution-1',
            child_status: 'completed',
            outputs: { status: 'ready' },
          },
        }}
        triggers={undefined}
        activeView="schema"
        searchTerm=""
      />
    )

    const outputField = screen.getByRole('treeitem', { name: /^T status/ })
    expect(within(outputField).getByText('Public status')).toBeInTheDocument()
    expect(within(outputField).getByText('ready')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Expected output fields help' }))
    expect(
      screen.getByText(
        'Required fields must be produced or the child run fails. Optional fields may be omitted if their source step does not run.'
      )
    ).toBeInTheDocument()
  })

  it('renders a large declared output contract without exposing internal step groups', () => {
    const outputFields = Array.from({ length: 64 }, (_, index) => ({
      name: `public_output_${index}`,
      type: 'string' as const,
      description: `Public field ${index}`,
    }))
    const outputSchema = {
      type: 'object',
      properties: Object.fromEntries(outputFields.map((field) => [field.name, { type: field.type }])),
    }
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        selectedTriggerNodeId: 'child-entry',
        isEligible: true,
        childSteps: [
          {
            id: '__declared_outputs__',
            name: 'Declared Outputs',
            type: 'subworkflow_declared_outputs',
            outputSchema,
            outputFields,
          },
        ],
      })
    )

    renderInputNodeContent()

    // Child step groups are collapsed by default for scannability
    // Tree should render with groups (child steps are collapsed so their fields aren't in DOM yet)
    const tree = screen.getByRole('tree', { name: 'Schema preview' })
    expect(tree).toBeInTheDocument()

    const treeItems = screen.getAllByRole('treeitem')
    expect(treeItems.length).toBeGreaterThan(64)
    expect(screen.getByText('T public_output_0')).toBeInTheDocument()
    expect(screen.queryByText('{} Child step 0')).not.toBeInTheDocument()
  })

  it('shows aggregate fields only and an access message after a 403', () => {
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        error: new ChildWorkflowSchemaFetchError('Forbidden', 403),
        isAccessDenied: true,
      })
    )

    renderInputNodeContent()

    expect(screen.getByText(/permission to view the child workflow/i)).toBeInTheDocument()
    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.queryByText('T stdout')).not.toBeInTheDocument()
  })

  it('shows aggregate fields and a retry action after a lookup error', async () => {
    const retry = vi.fn()
    vi.mocked(useChildWorkflowSchema).mockReturnValue(makeSchemaState({ error: new Error('Network error'), retry }))
    const user = userEvent.setup()

    renderInputNodeContent()

    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.queryByText('T stdout')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('explains when the published child workflow is unavailable', () => {
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        error: new ChildWorkflowSchemaFetchError('Not found', 404),
        isNotFound: true,
      })
    )

    renderInputNodeContent()

    expect(screen.getByText('Published child workflow is unavailable')).toBeInTheDocument()
    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.queryByText('T stdout')).not.toBeInTheDocument()
  })
})
