import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FieldErrorMessage, HintOrError } from './formFieldHelpers'

describe('FieldErrorMessage', () => {
  it('renders nothing when no error', () => {
    const { container } = render(<FieldErrorMessage />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders error message', () => {
    render(<FieldErrorMessage error={{ type: 'required', message: 'Field is required' }} />)
    expect(screen.getByText('Field is required')).toBeInTheDocument()
  })

  it('has no accessibility violations with error', async () => {
    const { container } = render(<FieldErrorMessage error={{ type: 'required', message: 'Field is required' }} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('HintOrError', () => {
  it('renders hint text when no error', () => {
    render(<HintOrError hint="Enter a valid URL" />)
    expect(screen.getByText('Enter a valid URL')).toBeInTheDocument()
  })

  it('renders error message instead of hint when error exists', () => {
    render(<HintOrError hint="Enter a valid URL" error={{ type: 'pattern', message: 'Invalid URL format' }} />)
    expect(screen.getByText('Invalid URL format')).toBeInTheDocument()
    expect(screen.queryByText('Enter a valid URL')).not.toBeInTheDocument()
  })

  it('has no accessibility violations with hint', async () => {
    const { container } = render(<HintOrError hint="Enter a value" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with error', async () => {
    const { container } = render(<HintOrError hint="Enter a value" error={{ type: 'required', message: 'Required' }} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
