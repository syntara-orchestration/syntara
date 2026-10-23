import type { Activity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SubWorkflowNodeDetails } from './SubWorkflowNodeDetails'

const mocks = vi.hoisted(() => ({ updateActivity: vi.fn(), showError: vi.fn() }))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStoreActions: () => ({ updateActivity: mocks.updateActivity }),
}))
vi.mock('../../../providers/alerts', () => ({ useAlerts: () => ({ showError: mocks.showError }) }))
vi.mock('../node-forms/SubWorkflowNodeForm', () => ({
  SubWorkflowNodeForm: ({
    initialData,
    onSubmit,
  }: {
    initialData?: Record<string, unknown>
    onSubmit: (data: Record<string, unknown>) => void
  }) => (
    <>
      <output data-testid="initial-data">{JSON.stringify(initialData)}</output>
      <button
        type="button"
        onClick={() =>
          onSubmit({
            name: 'Updated child step',
            workflow_id: 'workflow-2',
            trigger_node_id: 'sub-trigger-2',
            input_mapping: { region: 'west' },
          })
        }
      >
        Save test form
      </button>
    </>
  ),
}))

describe('SubWorkflowNodeDetails', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads persisted parameters and saves edited values back to the activity', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const taskData: Activity = {
      id: 'parent-node-1',
      type: 'sub_workflow',
      name: 'Existing child step',
      parameters: {
        workflow_id: 'workflow-1',
        trigger_node_id: 'sub-trigger-1',
        input_mapping: { host: '${lookup.hostname}', port: 22 },
      },
      settings: { timeout: 60 },
    }

    render(
      <SubWorkflowNodeDetails
        taskData={taskData}
        nodeId="parent-node-1"
        onClose={onClose}
        onHeaderContentChange={vi.fn()}
        projectId="project-1"
      />
    )

    expect(screen.getByTestId('initial-data')).toHaveTextContent(
      JSON.stringify({
        name: 'Existing child step',
        workflow_id: 'workflow-1',
        trigger_node_id: 'sub-trigger-1',
        input_mapping: { host: '${lookup.hostname}', port: 22 },
        settings: { timeout: 60 },
      })
    )

    await user.click(screen.getByRole('button', { name: 'Save test form' }))

    expect(mocks.updateActivity).toHaveBeenCalledWith(
      'parent-node-1',
      expect.objectContaining({
        name: 'Updated child step',
        type: 'sub_workflow',
        parameters: {
          workflow_id: 'workflow-2',
          trigger_node_id: 'sub-trigger-2',
          input_mapping: { region: 'west' },
        },
      })
    )
    expect(onClose).toHaveBeenCalledOnce()
    expect(mocks.showError).not.toHaveBeenCalled()
  })
})
