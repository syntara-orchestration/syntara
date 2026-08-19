import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldError, FormFieldWarning } from './FormFieldError'

describe('FormFieldError', () => {
  it('renders nothing when message is omitted', () => {
    const { container } = render(<FormFieldError />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders error message when provided', () => {
    render(<FormFieldError message="Project is required" />)
    expect(screen.getByText('Project is required')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FormFieldError message="Select at least one role" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('FormFieldWarning', () => {
  it('renders nothing when message is omitted', () => {
    const { container } = render(<FormFieldWarning />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders warning message when provided', () => {
    render(<FormFieldWarning message="Unable to check existing assignments" />)
    expect(screen.getByText('Unable to check existing assignments')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FormFieldWarning message="Unable to check existing assignments" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
