import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { TerraformTaskDetails } from './TerraformTaskDetails'

const mockUpdateActivity = vi.fn()
const mockShowError = vi.fn()
const mockOnClose = vi.fn()
const mockOnHeaderContentChange = vi.fn()

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStoreActions: () => ({ updateActivity: mockUpdateActivity }),
}))

vi.mock('../node-forms/TerraformNodeForm', () => ({
  TerraformNodeForm: ({
    onSubmit,
    subtypeId,
    initialData,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    subtypeId?: string
    initialData?: Record<string, unknown>
  }) => (
    <div data-testid="terraform-node-form">
      <span data-testid="subtype-id">{subtypeId}</span>
      <span data-testid="initial-name">{typeof initialData?.name === 'string' ? initialData.name : ''}</span>
      <span data-testid="initial-name-field">
        {typeof initialData?.name_field === 'string' ? initialData.name_field : ''}
      </span>
      <span data-testid="initial-targets">
        {typeof initialData?.target_resources === 'string' ? initialData.target_resources : ''}
      </span>
      <button
        type="button"
        data-testid="submit-success"
        onClick={() =>
          onSubmit({
            name: 'Updated TFE step',
            workspace_id: 'ws-1',
            integration_id: '11111111-1111-1111-1111-111111111111',
            credential_id: '22222222-2222-2222-2222-222222222222',
          })
        }
      >
        Submit
      </button>
      <button
        type="button"
        data-testid="submit-error"
        onClick={() => {
          mockUpdateActivity.mockImplementationOnce(() => {
            throw new Error('persist failed')
          })
          onSubmit({
            name: 'Broken step',
            workspace_id: 'ws-1',
          })
        }}
      >
        Submit error
      </button>
      <button
        type="button"
        data-testid="submit-non-error"
        onClick={() => {
          mockUpdateActivity.mockImplementationOnce(() => {
            // eslint-disable-next-line @typescript-eslint/only-throw-error -- exercise non-Error catch path
            throw 'string-failure'
          })
          onSubmit({ name: 'Broken step' })
        }}
      >
        Submit non-Error
      </button>
    </div>
  ),
}))

describe('TerraformTaskDetails', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('maps executor underscores to subtype id and hydrates initial data', () => {
    render(
      <TerraformTaskDetails
        executor="tfe_create_workspace"
        config={{ name: 'ws-from-config', target_resources: ['aws_instance.web', 'aws_instance.db'] }}
        taskData={{
          id: 'node-1',
          type: 'tfe_create_workspace',
          name: 'Create WS',
          parameters: {},
        }}
        nodeId="node-1"
        onClose={mockOnClose}
        onHeaderContentChange={mockOnHeaderContentChange}
      />
    )

    expect(screen.getByTestId('subtype-id')).toHaveTextContent('tfe-create-workspace')
    expect(screen.getByTestId('initial-name')).toHaveTextContent('Create WS')
    expect(screen.getByTestId('initial-name-field')).toHaveTextContent('ws-from-config')
    expect(screen.getByTestId('initial-targets')).toHaveTextContent('aws_instance.web, aws_instance.db')
  })

  it('updates the activity and closes on successful submit', async () => {
    const user = userEvent.setup()
    render(
      <TerraformTaskDetails
        executor="tfe_list_workspaces"
        config={{}}
        taskData={{
          id: 'node-2',
          type: 'tfe_list_workspaces',
          name: 'List WS',
          parameters: {},
        }}
        nodeId="node-2"
        onClose={mockOnClose}
        onHeaderContentChange={mockOnHeaderContentChange}
      />
    )

    await user.click(screen.getByTestId('submit-success'))

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'node-2',
      expect.objectContaining({
        name: 'Updated TFE step',
        parameters: expect.objectContaining({
          workspace_id: 'ws-1',
          integration_id: '11111111-1111-1111-1111-111111111111',
        }) as Record<string, unknown>,
      })
    )
    expect(mockOnClose).toHaveBeenCalledOnce()
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('shows an error alert when updateActivity throws an Error', async () => {
    const user = userEvent.setup()
    render(
      <TerraformTaskDetails
        executor="tfe_delete_workspace"
        config={{}}
        taskData={{
          id: 'node-3',
          type: 'tfe_delete_workspace',
          name: 'Delete WS',
          parameters: {},
        }}
        nodeId="node-3"
        onClose={mockOnClose}
        onHeaderContentChange={mockOnHeaderContentChange}
      />
    )

    await user.click(screen.getByTestId('submit-error'))

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Update failed',
      description: 'persist failed',
    })
    expect(mockOnClose).not.toHaveBeenCalled()
  })

  it('shows a generic error when updateActivity throws a non-Error', async () => {
    const user = userEvent.setup()
    render(
      <TerraformTaskDetails
        executor="tfe_add_variable"
        config={{}}
        taskData={{
          id: 'node-4',
          type: 'tfe_add_variable',
          name: 'Add var',
          parameters: {},
        }}
        nodeId="node-4"
        onClose={mockOnClose}
        onHeaderContentChange={mockOnHeaderContentChange}
      />
    )

    await user.click(screen.getByTestId('submit-non-error'))

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Update failed',
      description: 'Failed to update step',
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TerraformTaskDetails
        executor="tfe_create_workspace"
        config={{}}
        taskData={{
          id: 'node-a11y',
          type: 'tfe_create_workspace',
          name: 'Create WS',
          parameters: {},
        }}
        nodeId="node-a11y"
        onClose={mockOnClose}
        onHeaderContentChange={mockOnHeaderContentChange}
      />
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
