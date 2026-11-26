import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useWorkflowUsedBy } from '../workflows/useWorkflowUsedBy'

import { PublishWorkflowDialog } from './PublishWorkflowDialog'

vi.mock('../workflows/useWorkflowUsedBy', () => ({
  useWorkflowUsedBy: vi.fn(() => ({
    totalCount: 0,
    referencingParents: [],
    next: null,
    prev: null,
    isLoading: false,
    isError: false,
  })),
}))

const defaultProps = {
  isOpen: true,
  isPublishing: false,
  onClose: vi.fn(),
  onPublish: vi.fn(),
}

const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderWithClient(ui: ReactElement) {
  return render(<QueryClientProvider client={testQueryClient}>{ui}</QueryClientProvider>)
}

describe('PublishWorkflowDialog', () => {
  beforeEach(() => {
    vi.mocked(useWorkflowUsedBy).mockReturnValue({
      totalCount: 0,
      referencingParents: [],
      next: null,
      prev: null,
      isLoading: false,
      isError: false,
    })
  })

  it('renders the dialog with title', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByText('Publish workflow?')).toBeInTheDocument()
  })

  it('renders explanatory body text', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByText(/This will override any previously published workflow/i)).toBeInTheDocument()
  })

  it('renders version name input with default date value', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)
    const input = screen.getByLabelText('Version name')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('value', expect.stringMatching(/\w+ \d+, \d{4}/))
  })

  it('renders description textarea', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)
    expect(screen.getByLabelText('Description')).toBeInTheDocument()
  })

  it('description textarea accumulates typed characters', async () => {
    const user = userEvent.setup()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)

    const descInput = screen.getByLabelText('Description')
    await user.type(descInput, 'hello')

    expect(descInput).toHaveValue('hello')
  })

  it('calls onPublish with version name and description on submit', async () => {
    const user = userEvent.setup()
    const onPublish = vi.fn()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} onPublish={onPublish} />)

    const nameInput = screen.getByLabelText('Version name')
    await user.clear(nameInput)
    await user.type(nameInput, 'v1.0')
    await user.type(screen.getByLabelText('Description'), 'Initial release')
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(onPublish).toHaveBeenCalledWith('v1.0', 'Initial release', { confirm: false })
  })

  it('submits with default name when unchanged', async () => {
    const user = userEvent.setup()
    const onPublish = vi.fn()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} onPublish={onPublish} />)

    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(onPublish).toHaveBeenCalledWith(expect.stringMatching(/\w+ \d+, \d{4}/) as unknown, undefined, {
      confirm: false,
    })
  })

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalled()
  })

  it('shows breaking output changes and requires explicit publish confirmation', async () => {
    const user = userEvent.setup()
    const onConfirmContractChanges = vi.fn()
    renderWithClient(
      <PublishWorkflowDialog
        {...defaultProps}
        breakingChanges={[
          {
            trigger_id: 'child-trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'removed_output',
                field_path: 'release_tag',
                old_type: 'string',
                new_type: null,
                description: 'Removed output: release_tag',
              },
            ],
          },
        ]}
        onConfirmContractChanges={onConfirmContractChanges}
      />
    )

    expect(screen.getByText('Breaking output contract changes')).toBeInTheDocument()
    expect(
      screen.getByText(
        'This version removes the output “release_tag”. Published parent workflows will use the updated child version on their next run.'
      )
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /Breaking output contract changes/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'View output change details' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Publish anyway' }))

    expect(onConfirmContractChanges).toHaveBeenCalledWith(expect.stringMatching(/\w+ \d+, \d{4}/), undefined)
    expect(defaultProps.onPublish).not.toHaveBeenCalled()
  })

  it('carries trigger-removal confirmation through the output-contract confirmation flow', async () => {
    const user = userEvent.setup()
    const onConfirmContractChanges = vi.fn()
    vi.mocked(useWorkflowUsedBy).mockImplementation((_workflowId, options) => ({
      totalCount: options?.triggerNodeIds?.length ? 2 : 5,
      referencingParents: [],
      next: null,
      prev: null,
      isLoading: false,
      isError: false,
    }))

    renderWithClient(
      <PublishWorkflowDialog
        {...defaultProps}
        workflowId="child-workflow"
        removedTriggerNodeIds={['removed-trigger']}
        breakingChanges={[
          {
            trigger_id: 'child-trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'removed_output',
                field_path: 'release_tag',
                old_type: 'string',
                new_type: null,
                description: 'Removed output: release_tag',
              },
            ],
          },
        ]}
        onConfirmContractChanges={onConfirmContractChanges}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Publish anyway' }))

    expect(onConfirmContractChanges).toHaveBeenCalledWith(expect.stringMatching(/\w+ \d+, \d{4}/), undefined, {
      confirm: true,
    })
  })

  it('shows published parent references for non-breaking output changes before publishing', async () => {
    const user = userEvent.setup()
    const onConfirmContractChanges = vi.fn()
    renderWithClient(
      <PublishWorkflowDialog
        {...defaultProps}
        contractChanges={[
          {
            trigger_id: 'child-trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'added_output',
                field_path: 'release.notes',
                old_type: null,
                new_type: 'string',
                description: 'Added optional output: release.notes',
                is_breaking: false,
              },
            ],
          },
        ]}
        parentWorkflows={[
          {
            workflow_id: 'parent-id',
            workflow_name: 'Deploy parent',
            workflow_version: 2,
            step_id: 'invoke_child',
            step_name: 'Invoke child',
          },
        ]}
        onConfirmContractChanges={onConfirmContractChanges}
      />
    )

    expect(
      screen.getByText(
        'This version adds the optional output “release.notes”. Published parent workflows will use the updated child version on their next run.'
      )
    ).toBeInTheDocument()
    expect(screen.getByText('Used by 1 visible published workflow')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /view visible parent workflows/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Publish with changes' }))
    expect(onConfirmContractChanges).toHaveBeenCalledWith(expect.stringMatching(/\w+ \d+, \d{4}/), undefined)
  })

  it('disables buttons when publishing', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} isPublishing={true} />)

    expect(screen.getByRole('button', { name: /Publish/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('does not render when closed', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} isOpen={false} />)
    expect(screen.queryByText('Publish workflow?')).not.toBeInTheDocument()
  })

  it('shows validation error when version name is cleared', async () => {
    const user = userEvent.setup()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)

    const nameInput = screen.getByLabelText('Version name')
    await user.clear(nameInput)
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(defaultProps.onPublish).not.toHaveBeenCalled()
    expect(screen.getByText('Version name is required')).toBeInTheDocument()
  })

  it('shows validation error when description exceeds 1000 characters', async () => {
    const user = userEvent.setup()
    renderWithClient(<PublishWorkflowDialog {...defaultProps} />)

    const descInput = screen.getByLabelText('Description')
    await user.click(descInput)
    await user.paste('x'.repeat(1001))
    await user.click(screen.getByRole('button', { name: 'Publish workflow' }))

    expect(defaultProps.onPublish).not.toHaveBeenCalled()
    expect(screen.getByText('Description must be 1000 characters or fewer')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithClient(<PublishWorkflowDialog {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows the combined "N of M" impact when a trigger is removed', () => {
    vi.mocked(useWorkflowUsedBy).mockImplementation((_id, options) => ({
      totalCount: options?.triggerNodeIds?.length ? 13 : 25,
      referencingParents: [],
      next: null,
      prev: null,
      isLoading: false,
      isError: false,
    }))

    renderWithClient(
      <PublishWorkflowDialog {...defaultProps} workflowId="wf-1" removedTriggerNodeIds={['trigger_a']} />
    )

    expect(
      screen.getByText(/Removing the workflow trigger will affect 13 of 25 published workflows using this workflow/)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/no longer be able to invoke this workflow through the removed trigger/)
    ).toBeInTheDocument()
  })

  it('shows the total and future-runs note when no trigger is removed', () => {
    vi.mocked(useWorkflowUsedBy).mockReturnValue({
      totalCount: 25,
      referencingParents: [],
      next: null,
      prev: null,
      isLoading: false,
      isError: false,
    })

    renderWithClient(<PublishWorkflowDialog {...defaultProps} workflowId="wf-1" />)

    expect(screen.getByText(/25 published workflows use this workflow as a sub-workflow/)).toBeInTheDocument()
    expect(screen.getByText(/Future sub-workflow runs will use this version/)).toBeInTheDocument()
  })

  it('blocks publishing while the trigger diff is still resolving', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} workflowId="wf-1" triggerDiffLoading />)

    expect(screen.getByRole('button', { name: 'Publish workflow' })).toBeDisabled()
    expect(screen.getByText(/Checking dependency impact/)).toBeInTheDocument()
  })

  it('blocks publishing and warns when the trigger diff cannot be verified', () => {
    renderWithClient(<PublishWorkflowDialog {...defaultProps} workflowId="wf-1" triggerDiffError />)

    expect(screen.getByRole('button', { name: 'Publish workflow' })).toBeDisabled()
    expect(screen.getByText(/Can't verify dependency impact/)).toBeInTheDocument()
  })
})
