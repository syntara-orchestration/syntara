import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { WorkflowSelectorFeedback } from './WorkflowSelectorFeedback'

type Props = Parameters<typeof WorkflowSelectorFeedback>[0]

function buildProps(overrides: Partial<Props> = {}): Props {
  return {
    workflowError: undefined,
    hasError: false,
    errorVariant: 'danger',
    errorMessage: '',
    hasOptions: false,
    showEligibilityHelp: false,
    hasSearchTerm: false,
    hasProject: false,
    onRetry: vi.fn(),
    ...overrides,
  }
}

describe('WorkflowSelectorFeedback', () => {
  it('renders nothing when there is no error and no eligibility help', () => {
    const { container } = render(<WorkflowSelectorFeedback {...buildProps()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the workflow error message', () => {
    render(<WorkflowSelectorFeedback {...buildProps({ workflowError: 'Boom while loading' })} />)
    expect(screen.getByText('Boom while loading')).toBeInTheDocument()
  })

  it('shows a verified-selectable alert with a working Retry when there is an error and options exist', async () => {
    const onRetry = vi.fn()
    render(
      <WorkflowSelectorFeedback
        {...buildProps({
          hasError: true,
          hasOptions: true,
          errorMessage: 'Some workflows failed to verify',
          onRetry,
        })}
      />
    )
    expect(screen.getByText('Some workflows failed to verify')).toBeInTheDocument()
    expect(screen.getByText(/Successfully verified workflows remain selectable/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('prompts to retry when there is an error and no options', () => {
    render(
      <WorkflowSelectorFeedback {...buildProps({ hasError: true, hasOptions: false, errorMessage: 'Lookup failed' })} />
    )
    expect(screen.getByText(/Retry to check for eligible workflows/)).toBeInTheDocument()
  })

  it('tells the user to select a project when eligibility help shows without a project', () => {
    render(<WorkflowSelectorFeedback {...buildProps({ showEligibilityHelp: true, hasProject: false })} />)
    expect(screen.getByText('Select a project to choose a child workflow.')).toBeInTheDocument()
    expect(screen.queryByText(/enabled, published workflows in this project/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Refresh workflows' })).not.toBeInTheDocument()
  })

  it('shows the no-match text and no refresh button while a search term is active', () => {
    render(
      <WorkflowSelectorFeedback {...buildProps({ showEligibilityHelp: true, hasProject: true, hasSearchTerm: true })} />
    )
    expect(screen.getByText('No workflows match your search.')).toBeInTheDocument()
    expect(screen.getByText(/enabled, published workflows in this project/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Refresh workflows' })).not.toBeInTheDocument()
  })

  it('shows the no-eligible text with a working Refresh button when no search term is active', async () => {
    const onRetry = vi.fn()
    render(
      <WorkflowSelectorFeedback
        {...buildProps({ showEligibilityHelp: true, hasProject: true, hasSearchTerm: false, onRetry })}
      />
    )
    expect(screen.getByText('No eligible workflows found.')).toBeInTheDocument()
    expect(screen.getByText(/enabled, published workflows in this project/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh workflows' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
