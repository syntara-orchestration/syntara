import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WorkflowReferencedParentsAlert } from './WorkflowReferencedParentsAlert'

describe('WorkflowReferencedParentsAlert', () => {
  it('renders nothing when there are no references and no error', () => {
    const { container } = render(<WorkflowReferencedParentsAlert totalCount={0} isError={false} title="t" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a fetch-error alert when the check failed', () => {
    render(<WorkflowReferencedParentsAlert totalCount={0} isError title="t" />)
    expect(screen.getByText(/Unable to check which workflows use this workflow/)).toBeInTheDocument()
  })

  it('shows the affected count as a badge without listing parent names', () => {
    render(
      <WorkflowReferencedParentsAlert
        totalCount={5}
        isError={false}
        title="Impact warning"
        consequence="They will no longer be able to call it."
      />
    )
    expect(screen.getByText('Impact warning')).toBeInTheDocument()
    expect(screen.getByText('They will no longer be able to call it.')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })
})
