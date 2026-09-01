import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldError, FormFieldHintOrError, FormFieldWarning } from './FormFieldError'

describe('FormFieldError', () => {
  it('renders nothing when message and error are omitted', () => {
    const { container } = render(<FormFieldError />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders error message when message is provided', () => {
    render(<FormFieldError message="Project is required" />)
    expect(screen.getByText('Project is required')).toBeInTheDocument()
  })

  it('renders error message from react-hook-form FieldError', () => {
    render(<FormFieldError error={{ type: 'required', message: 'Field is required' }} />)
    expect(screen.getByText('Field is required')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FormFieldError message="Select at least one role" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('FormFieldHintOrError', () => {
  it('renders hint text when no error', () => {
    render(<FormFieldHintOrError hint="Enter a valid URL" />)
    expect(screen.getByText('Enter a valid URL')).toBeInTheDocument()
  })

  it('renders error message instead of hint when error exists', () => {
    render(<FormFieldHintOrError hint="Enter a valid URL" error={{ type: 'pattern', message: 'Invalid URL format' }} />)
    expect(screen.getByText('Invalid URL format')).toBeInTheDocument()
    expect(screen.queryByText('Enter a valid URL')).not.toBeInTheDocument()
  })

  it('has no accessibility violations with hint', async () => {
    const { container } = render(<FormFieldHintOrError hint="Enter a value" />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with error', async () => {
    const { container } = render(
      <FormFieldHintOrError hint="Enter a value" error={{ type: 'required', message: 'Required' }} />
    )
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
