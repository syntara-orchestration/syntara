import { ActivityTypeEnum, getNodeOutputSchema } from '@syntara/contracts'
import { fireEvent, render, screen } from '@testing-library/react'
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

function childStep(): ChildWorkflowStepSchema {
  return {
    id: 'deploy_app',
    name: 'Deploy application',
    type: ActivityTypeEnum.SCRIPT,
    outputSchema: { type: 'object' },
    outputFields: getNodeOutputSchema(ActivityTypeEnum.SCRIPT),
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
        childSteps: [childStep()],
      })
    )

    const { container } = renderInputNodeContent()

    // Aggregate fields should be visible
    expect(screen.getByText('T child_workflow_id')).toBeInTheDocument()
    expect(screen.getByRole('tree', { name: 'Schema preview' })).toBeInTheDocument()

    // Child step group should be present (collapsed by default for scannability)
    // Groups have type prefix: {} for objects
    expect(screen.getByText('{} Deploy application')).toBeInTheDocument()

    // Expand the child step group to access its fields
    const childStepToggle = screen.getByRole('button', { name: /Deploy application/i })
    const user = userEvent.setup()
    await user.click(childStepToggle)

    // Now the child fields should be visible
    expect(screen.getByText('T stdout')).toBeInTheDocument()

    const dragCalls: Array<[string, string]> = []
    fireEvent.dragStart(screen.getByText('T stdout'), {
      dataTransfer: {
        setData: (format: string, value: string) => dragCalls.push([format, value]),
        effectAllowed: '',
      },
    })
    expect(dragCalls.find(([format]) => format === 'text/plain')?.[1]).toBe(
      '${invoke_child.Result.outputs.deploy_app.stdout}'
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders output groups for a 64-step child workflow', () => {
    const scriptOutputFields = getNodeOutputSchema(ActivityTypeEnum.SCRIPT)
    expect(scriptOutputFields).not.toBeNull()
    vi.mocked(useChildWorkflowSchema).mockReturnValue(
      makeSchemaState({
        selectedTriggerNodeId: 'child-entry',
        isEligible: true,
        childSteps: Array.from({ length: 64 }, (_, index) => ({
          id: `child_step_${index}`,
          name: `Child step ${index}`,
          type: ActivityTypeEnum.SCRIPT,
          outputSchema: { type: 'object' },
          outputFields: scriptOutputFields,
        })),
      })
    )

    renderInputNodeContent()

    // Child step groups are collapsed by default for scannability
    // Tree should render with groups (child steps are collapsed so their fields aren't in DOM yet)
    const tree = screen.getByRole('tree', { name: 'Schema preview' })
    expect(tree).toBeInTheDocument()

    // Verify tree items are rendered (collapsed groups + top-level aggregate fields)
    const treeItems = screen.getAllByRole('treeitem')
    // Should have Result, child_execution_id, child_workflow_id, child_workflow_name, child_workflow_version, child_status, outputs, and 64 child step groups
    expect(treeItems.length).toBeGreaterThan(64)
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
