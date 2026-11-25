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
    render(
      <>
        <input aria-label="Project name" aria-describedby="project-error" />
        <FormFieldError id="project-error" message="Project is required" />
      </>
    )
    expect(screen.getByRole('textbox', { name: 'Project name' })).toHaveAccessibleDescription(/Project is required/)
  })

  it('renders error message from react-hook-form FieldError', () => {
    render(<FormFieldError error={{ type: 'required', message: 'Field is required' }} />)
    expect(screen.getByText('Field is required')).toBeInTheDocument()
  })

  it('renders nothing when the field error has no message', () => {
    const { container } = render(<FormFieldError id="project-error" error={{ type: 'manual' }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FormFieldError message="Select at least one role" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('FormFieldHintOrError', () => {
  it('renders hint text when no error', () => {
    render(
      <>
        <input aria-label="URL" aria-describedby="url-helper" />
        <FormFieldHintOrError id="url-helper" hint="Enter a valid URL" />
      </>
    )
    expect(screen.getByRole('textbox', { name: 'URL' })).toHaveAccessibleDescription('Enter a valid URL')
  })

  it('renders error message instead of hint when error exists', () => {
    render(
      <>
        <input aria-label="URL" aria-describedby="url-helper" />
        <FormFieldHintOrError
          id="url-helper"
          hint="Enter a valid URL"
          error={{ type: 'pattern', message: 'Invalid URL format' }}
        />
      </>
    )
    expect(screen.getByRole('textbox', { name: 'URL' })).toHaveAccessibleDescription(/Invalid URL format/)
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
