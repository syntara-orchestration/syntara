import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ChildWorkflowSelector, type ChildWorkflowSelectorProps } from './ChildWorkflowSelector'
import type { ChildWorkflowOption } from './useChildWorkflowSelector'

const singleTriggerOption: ChildWorkflowOption = {
  value: 'workflow-1',
  label: 'Child Workflow (v4)',
  description: 'Reusable child flow',
  triggers: [{ trigger_node_id: 'sub-trigger-1', name: 'Subworkflow Trigger', input_schema: {} }],
}

const multipleTriggerOption: ChildWorkflowOption = {
  value: 'workflow-2',
  label: 'Workflow with multiple triggers (v2)',
  triggers: [
    { trigger_node_id: 'first-trigger', name: 'First trigger', input_schema: {} },
    { trigger_node_id: 'second-trigger', name: 'Second trigger', input_schema: {} },
  ],
}

function buildProps(overrides: Partial<ChildWorkflowSelectorProps> = {}): ChildWorkflowSelectorProps {
  return {
    options: [singleTriggerOption, multipleTriggerOption],
    selectedWorkflowId: null,
    selectedTriggerNodeId: '',
    onWorkflowChange: vi.fn(),
    onTriggerChange: vi.fn(),
    setSearchTerm: vi.fn(),
    isLoading: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    onLoadMore: vi.fn(),
    hasError: false,
    errorMessage: 'Unable to verify eligible workflows.',
    errorVariant: 'danger',
    onRetry: vi.fn(),
    ...overrides,
  }
}

describe('ChildWorkflowSelector', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows eligible published workflows and their published versions', async () => {
    const user = userEvent.setup()
    render(<ChildWorkflowSelector {...buildProps()} />)

    const workflowInput = screen.getByRole('textbox', { name: 'Workflow' })
    await user.click(workflowInput)

    expect(screen.getByText('Child Workflow (v4)')).toBeInTheDocument()
    expect(screen.getByText('Workflow with multiple triggers (v2)')).toBeInTheDocument()
    expect(screen.getByText('Reusable child flow')).toBeInTheDocument()
  })

  it('selects the workflow and its only trigger together', async () => {
    const user = userEvent.setup()
    const props = buildProps()
    render(<ChildWorkflowSelector {...props} />)

    await user.click(screen.getByPlaceholderText('Search for a published workflow...'))
    await user.click(screen.getByText('Child Workflow (v4)'))

    expect(props.onWorkflowChange).toHaveBeenCalledWith('workflow-1', 'sub-trigger-1')
  })

  it('shows the only trigger as a read-only value instead of a selector', () => {
    render(
      <ChildWorkflowSelector
        {...buildProps({
          selectedWorkflowId: 'workflow-1',
          selectedOption: singleTriggerOption,
          selectedTriggerNodeId: '',
        })}
      />
    )

    const triggerField = screen.getByRole('textbox', { name: 'Workflow trigger' })
    expect(triggerField).toHaveValue('Subworkflow Trigger')
    expect(triggerField).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Workflow trigger' })).not.toBeInTheDocument()
  })

  it('debounces the workflow search term', async () => {
    const user = userEvent.setup()
    const props = buildProps()
    render(<ChildWorkflowSelector {...props} />)

    const input = screen.getByRole('textbox', { name: 'Workflow' })
    await user.click(input)
    await user.type(input, 'Child')

    await waitFor(() => expect(props.setSearchTerm).toHaveBeenLastCalledWith('Child'))
  })

  it('requires an explicit trigger selection when a workflow has multiple triggers', async () => {
    const user = userEvent.setup()
    const props = buildProps()
    render(<ChildWorkflowSelector {...props} />)

    await user.click(screen.getByPlaceholderText('Search for a published workflow...'))
    await user.click(screen.getByText('Workflow with multiple triggers (v2)'))
    expect(props.onWorkflowChange).toHaveBeenCalledWith('workflow-2', '')

    const selectedProps = buildProps({
      selectedWorkflowId: 'workflow-2',
      selectedOption: multipleTriggerOption,
    })
    render(<ChildWorkflowSelector {...selectedProps} />)
    await user.click(screen.getByRole('button', { name: 'Workflow trigger' }))
    await user.click(screen.getByText('Second trigger'))

    expect(selectedProps.onTriggerChange).toHaveBeenCalledWith('second-trigger')
  })

  it('clears the selected workflow', async () => {
    const user = userEvent.setup()
    const props = buildProps({
      selectedWorkflowId: 'workflow-1',
      selectedOption: singleTriggerOption,
      selectedTriggerNodeId: 'sub-trigger-1',
    })
    render(<ChildWorkflowSelector {...props} />)

    await user.click(screen.getByRole('button', { name: 'Clear selection' }))

    expect(props.onWorkflowChange).toHaveBeenCalledWith(null, '')
  })

  it('clears search text without clearing the selected workflow', async () => {
    const user = userEvent.setup()
    const props = buildProps({
      selectedWorkflowId: 'workflow-1',
      selectedOption: singleTriggerOption,
      selectedTriggerNodeId: 'sub-trigger-1',
    })
    render(<ChildWorkflowSelector {...props} />)

    const workflowInput = screen.getByRole('textbox', { name: 'Workflow' })
    await user.click(workflowInput)
    await user.type(workflowInput, 'missing')
    await user.click(screen.getByRole('button', { name: 'Clear search' }))

    expect(props.onWorkflowChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(workflowInput).toHaveValue('Child Workflow (v4)')
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
  })

  it('shows the selected workflow name when its option is not in the current results', () => {
    render(
      <ChildWorkflowSelector
        {...buildProps({
          options: [],
          selectedWorkflowId: 'workflow-outside-results',
          selectedWorkflowLabel: 'Selected workflow (v2)',
        })}
      />
    )

    expect(screen.getByRole('textbox', { name: 'Workflow' })).toHaveValue('Selected workflow (v2)')
  })

  it('loads the next workflow page from the picker menu', async () => {
    const user = userEvent.setup()
    const onLoadMore = vi.fn()
    render(<ChildWorkflowSelector {...buildProps({ hasNextPage: true, onLoadMore })} />)

    await user.click(screen.getByRole('textbox', { name: 'Workflow' }))
    await user.click(screen.getByRole('option', { name: 'Load more workflows' }))

    expect(onLoadMore).toHaveBeenCalledOnce()
  })

  it('shows an error when eligible workflows cannot be verified', () => {
    render(<ChildWorkflowSelector {...buildProps({ hasError: true })} />)

    expect(screen.getByRole('heading', { name: /Unable to verify eligible workflows/ })).toBeInTheDocument()
  })

  it('keeps verified workflows selectable and retries failed lookups', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(
      <ChildWorkflowSelector
        {...buildProps({
          hasError: true,
          errorMessage: 'Some workflows could not be checked because of permissions.',
          options: [singleTriggerOption],
          onRetry,
        })}
      />
    )

    expect(
      screen.getByRole('heading', { name: /Some workflows could not be checked because of permissions/ })
    ).toBeInTheDocument()
    expect(screen.getByText('Successfully verified workflows remain selectable.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('textbox', { name: 'Workflow' }))
    expect(screen.getByText('Child Workflow (v4)')).toBeInTheDocument()
  })

  it('explains how to make workflows eligible after a successful empty lookup', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<ChildWorkflowSelector {...buildProps({ options: [], onRetry })} />)

    expect(
      screen.getByText(
        /This picker shows enabled, published workflows in this project that have a Sub-workflow Trigger/
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText(/add a Sub-workflow Trigger to a child workflow in this project and publish it/)
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Refresh workflows' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('shows different help text when searching returns no results', async () => {
    const user = userEvent.setup()
    render(<ChildWorkflowSelector {...buildProps({ options: [] })} />)

    const workflowInput = screen.getByRole('textbox', { name: 'Workflow' })
    await user.click(workflowInput)
    await user.type(workflowInput, 'nonexistent')

    await waitFor(() => {
      expect(screen.getByText(/No workflows match your search/)).toBeInTheDocument()
      expect(
        screen.getByText(
          /This picker shows enabled, published workflows in this project that have a Sub-workflow Trigger/
        )
      ).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: 'Refresh workflows' })).not.toBeInTheDocument()
  })

  it('shows loading and empty states', async () => {
    const user = userEvent.setup()
    const props = buildProps({ options: [], isLoading: true })
    render(<ChildWorkflowSelector {...props} />)

    expect(screen.getByRole('progressbar', { name: 'Loading workflows' })).toBeInTheDocument()
    await user.click(screen.getByRole('textbox', { name: 'Workflow' }))
    expect(screen.getByText('Loading eligible workflows...')).toBeInTheDocument()
  })

  it('disables the selector and hides its clear control in version view', () => {
    render(
      <ChildWorkflowSelector
        {...buildProps({
          selectedWorkflowId: 'workflow-1',
          selectedOption: singleTriggerOption,
          selectedTriggerNodeId: 'sub-trigger-1',
          isDisabled: true,
        })}
      />
    )

    expect(screen.getByRole('textbox', { name: 'Workflow' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ChildWorkflowSelector {...buildProps()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
