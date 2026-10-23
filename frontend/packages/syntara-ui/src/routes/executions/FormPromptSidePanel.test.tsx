import type { FormsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptSidePanel } from './FormPromptSidePanel'

const mockFormPromptResponseOptions = vi.hoisted(() => ({
  includeFooterSlot: false,
}))

vi.mock('./FormPromptResponseContent', async () => {
  const { FormPromptRespondPanelFooterSlot } = await import('./formPrompt/FormPromptRespondPanelFooter')
  return {
    FormPromptResponseContent: ({ formPromptId }: { formPromptId: string }) => (
      <div aria-label="Form prompt response">
        Prompt {formPromptId}
        {mockFormPromptResponseOptions.includeFooterSlot ? (
          <FormPromptRespondPanelFooterSlot>
            <button type="button">Submit response</button>
          </FormPromptRespondPanelFooterSlot>
        ) : null}
      </div>
    ),
  }
})

const mockFormPrompt: FormsAPI.components['schemas']['FormPromptSummary'] = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'collect_input',
  name: 'Collect input',
  status: 'pending',
  temporal_activity_id: 'act-1',
}

describe('FormPromptSidePanel', () => {
  it('renders respond header and content', () => {
    render(
      <FormPromptSidePanel executionId="exec-1" formPrompt={mockFormPrompt} onClose={vi.fn()} onSubmitted={vi.fn()} />
    )

    expect(screen.getByRole('heading', { name: 'Respond to prompt' })).toBeInTheDocument()
    expect(screen.getByLabelText('Form prompt response')).toHaveTextContent(/Prompt fp-1/)
  })

  it('omits SynPanel footer when no submit actions are projected', () => {
    mockFormPromptResponseOptions.includeFooterSlot = false

    render(
      <FormPromptSidePanel executionId="exec-1" formPrompt={mockFormPrompt} onClose={vi.fn()} onSubmitted={vi.fn()} />
    )

    expect(screen.queryByRole('button', { name: 'Submit response' })).not.toBeInTheDocument()
  })

  it('projects respond actions into the SynPanel footer', async () => {
    mockFormPromptResponseOptions.includeFooterSlot = true

    render(
      <FormPromptSidePanel executionId="exec-1" formPrompt={mockFormPrompt} onClose={vi.fn()} onSubmitted={vi.fn()} />
    )

    const responseRegion = screen.getByLabelText('Form prompt response')
    const submitButton = await screen.findByRole('button', { name: 'Submit response' })
    expect(responseRegion).not.toContainElement(submitButton)
  })

  it('calls onClose when close is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <FormPromptSidePanel executionId="exec-1" formPrompt={mockFormPrompt} onClose={onClose} onSubmitted={vi.fn()} />
    )

    await user.click(screen.getByRole('button', { name: 'Close form prompt panel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('uses form-specific navigation button labels', () => {
    render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={mockFormPrompt}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
        currentIndex={1}
        totalCount={2}
        hasPrev
        hasNext
        onNavigatePrev={vi.fn()}
        onNavigateNext={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Previous prompt' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next prompt' })).toBeInTheDocument()
  })

  it('calls navigation handlers when prev and next are clicked', async () => {
    const user = userEvent.setup()
    const onNavigatePrev = vi.fn()
    const onNavigateNext = vi.fn()

    render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={mockFormPrompt}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
        currentIndex={1}
        totalCount={3}
        hasPrev
        hasNext
        onNavigatePrev={onNavigatePrev}
        onNavigateNext={onNavigateNext}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Previous prompt' }))
    await user.click(screen.getByRole('button', { name: 'Next prompt' }))
    expect(onNavigatePrev).toHaveBeenCalledOnce()
    expect(onNavigateNext).toHaveBeenCalledOnce()
  })

  it('renders the simple header when navigation is unavailable', () => {
    render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={mockFormPrompt}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
        totalCount={2}
      />
    )

    expect(screen.getByRole('heading', { name: 'Respond to prompt' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Previous prompt' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next prompt' })).not.toBeInTheDocument()
  })

  it('renders the simple header when only one prompt is in the queue', () => {
    render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={mockFormPrompt}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
        totalCount={1}
        onNavigatePrev={vi.fn()}
        onNavigateNext={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: 'Previous prompt' })).not.toBeInTheDocument()
  })

  it('forwards optional content props to the response surface', () => {
    render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={mockFormPrompt}
        activityNameMap={new Map([['collect_input', 'Collect input']])}
        workflowDefinition={{ nodes: [] }}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
      />
    )

    expect(screen.getByLabelText('Form prompt response')).toHaveTextContent(/Prompt fp-1/)
  })

  it('returns null when form prompt id is missing', () => {
    const { container } = render(
      <FormPromptSidePanel
        executionId="exec-1"
        formPrompt={{ ...mockFormPrompt, id: undefined as unknown as string }}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
      />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <FormPromptSidePanel executionId="exec-1" formPrompt={mockFormPrompt} onClose={vi.fn()} onSubmitted={vi.fn()} />
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
