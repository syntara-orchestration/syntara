import type { WorkflowAPI } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { WorkflowPublishDialog } from './WorkflowPublishDialog'

const mocks = vi.hoisted(() => ({ review: vi.fn() }))
const publishWorkflow = {
  id: 'workflow-id',
  name: 'Child workflow',
  description: null,
  labels: {},
  current_version: 4,
  is_enabled: true,
  is_builtin: false,
  project_id: 'project-id',
  created_at: '2026-11-14T00:00:00Z',
  updated_at: '2026-11-14T00:00:00Z',
} satisfies WorkflowAPI.components['schemas']['WorkflowRead']

function createPublishDialog(isOpen: boolean) {
  return { isOpen, item: publishWorkflow, open: vi.fn(), close: vi.fn() }
}

vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: () => ({
      data: { version: { workflow_definition: { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] } } },
      refetch: vi.fn(),
    }),
  },
}))

vi.mock('../builder/hooks/usePublishWorkflow', () => ({
  usePublishWorkflow: () => ({ reviewOutputContract: mocks.review, isPublishing: false }),
}))

vi.mock('../builder/PublishWorkflowDialog', () => ({
  PublishWorkflowDialog: ({
    isOpen,
    contractChanges,
    onPublish,
    onConfirmContractChanges,
  }: {
    isOpen: boolean
    contractChanges: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
    onPublish: (name?: string, description?: string) => void
    onConfirmContractChanges?: () => void
  }) =>
    isOpen ? (
      <div>
        <button type="button" onClick={() => onPublish('v2', 'Changed output contract')}>
          Review publish
        </button>
        {contractChanges.length > 0 && (
          <button type="button" onClick={onConfirmContractChanges}>
            Confirm publish
          </button>
        )}
      </div>
    ) : null,
}))

describe('WorkflowPublishDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('publishes immediately when the output contract has no changes', async () => {
    mocks.review.mockResolvedValue({
      has_breaking_changes: false,
      triggers: [],
      has_contract_changes: false,
      contract_changes: [],
      parent_workflows: [],
    })
    const onPublishWorkflow = vi.fn()
    const user = userEvent.setup()

    render(
      <WorkflowPublishDialog
        publishDialog={createPublishDialog(true)}
        isPublishing={false}
        onPublishWorkflow={onPublishWorkflow}
      />
    )
    await user.click(screen.getByRole('button', { name: 'Review publish' }))

    await waitFor(() =>
      expect(onPublishWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'workflow-id' }),
        'v2',
        'Changed output contract'
      )
    )
  })

  it('waits for confirmation when referenced workflows have output contract changes', async () => {
    mocks.review.mockResolvedValue({
      has_breaking_changes: false,
      triggers: [],
      has_contract_changes: true,
      contract_changes: [
        {
          trigger_id: 'child-trigger',
          changes: [
            {
              change_type: 'added_output',
              field_path: 'release.notes',
              description: 'Added optional output: release.notes',
              is_breaking: false,
            },
          ],
        },
      ],
      parent_workflows: [
        {
          workflow_id: 'parent-id',
          workflow_name: 'Deploy parent',
          workflow_version: 2,
          step_id: 'invoke-child',
          step_name: 'Invoke child',
        },
      ],
    })
    const onPublishWorkflow = vi.fn()
    const user = userEvent.setup()

    render(
      <WorkflowPublishDialog
        publishDialog={createPublishDialog(true)}
        isPublishing={false}
        onPublishWorkflow={onPublishWorkflow}
      />
    )
    await user.click(screen.getByRole('button', { name: 'Review publish' }))

    expect(await screen.findByRole('button', { name: 'Confirm publish' })).toBeInTheDocument()
    expect(onPublishWorkflow).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirm publish' }))

    expect(onPublishWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'workflow-id' }),
      'v2',
      'Changed output contract'
    )
  })

  it('renders an accessible closed state', async () => {
    const { container } = render(
      <WorkflowPublishDialog
        publishDialog={createPublishDialog(false)}
        isPublishing={false}
        onPublishWorkflow={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
