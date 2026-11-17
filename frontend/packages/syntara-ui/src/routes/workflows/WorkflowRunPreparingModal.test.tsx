import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { WorkflowRunPreparingModal } from './WorkflowRunPreparingModal'

describe('WorkflowRunPreparingModal', () => {
  it('has no accessibility violations when open', async () => {
    const { container } = render(<WorkflowRunPreparingModal isOpen onClose={() => undefined} />)

    expect(screen.getByRole('dialog', { name: 'Preparing workflow run' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
