import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SubWorkflowTriggerFields } from './SubWorkflowTriggerFields'

// The payload section renders a heavy code editor and needs form context; mock it
// so the test exercises SubWorkflowTriggerFields' own rendering and the error wiring.
vi.mock('./PayloadValidationSection', () => ({
  PayloadValidationSection: ({ error }: Readonly<{ error?: string }>) => (
    <div data-testid="payload-validation-section">{error ?? 'no-error'}</div>
  ),
}))

describe('SubWorkflowTriggerFields', () => {
  it('renders the info callout and passes no error when errors is empty', () => {
    render(<SubWorkflowTriggerFields errors={{}} />)

    expect(screen.getByText(/can be called from another workflow/i)).toBeInTheDocument()
    expect(screen.getByText('Workflow trigger')).toBeInTheDocument()
    expect(screen.getByTestId('payload-validation-section')).toHaveTextContent('no-error')
  })

  it('passes the input-schema error message through to the payload section', () => {
    render(<SubWorkflowTriggerFields errors={{ inputSchema: { message: 'Invalid schema' } }} />)

    expect(screen.getByTestId('payload-validation-section')).toHaveTextContent('Invalid schema')
  })

  it('handles an inputSchema error object without a message', () => {
    render(<SubWorkflowTriggerFields errors={{ inputSchema: {} }} />)

    expect(screen.getByTestId('payload-validation-section')).toHaveTextContent('no-error')
  })
})
