import type { FormsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptSidePanel } from './FormPromptSidePanel'

vi.mock('./FormPromptResponseContent', () => ({
  FormPromptResponseContent: ({ formPromptId }: { formPromptId: string }) => (
    <div aria-label="Form prompt response">Prompt {formPromptId}</div>
  ),
}))

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
    expect(screen.getByLabelText('Form prompt response')).toHaveTextContent('Prompt fp-1')
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
