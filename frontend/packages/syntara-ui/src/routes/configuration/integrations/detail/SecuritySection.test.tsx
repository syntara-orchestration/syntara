import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SecuritySection } from './SecuritySection'

describe('SecuritySection', () => {
  it('returns null when configuration is undefined', () => {
    const { container } = render(<SecuritySection configuration={undefined as never} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('returns null when configuration lacks allow_http', () => {
    const { container } = render(<SecuritySection configuration={{ insecure_skip_tls_verify: false } as never} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('returns null when configuration lacks insecure_skip_tls_verify', () => {
    const { container } = render(<SecuritySection configuration={{ allow_http: false } as never} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders Security heading when both fields are present', () => {
    render(<SecuritySection configuration={{ allow_http: false, insecure_skip_tls_verify: false } as never} />)

    expect(screen.getByRole('heading', { name: 'Security' })).toBeInTheDocument()
  })

  it('shows "HTTPS only" when allow_http is false', () => {
    render(<SecuritySection configuration={{ allow_http: false, insecure_skip_tls_verify: false } as never} />)

    expect(screen.getByText('HTTPS only')).toBeInTheDocument()
  })

  it('shows "HTTP allowed" warning when allow_http is true', () => {
    render(<SecuritySection configuration={{ allow_http: true, insecure_skip_tls_verify: false } as never} />)

    expect(screen.getByText('HTTP allowed')).toBeInTheDocument()
    expect(screen.queryByText('HTTPS only')).not.toBeInTheDocument()
  })

  it('shows "Enabled" when insecure_skip_tls_verify is false', () => {
    render(<SecuritySection configuration={{ allow_http: false, insecure_skip_tls_verify: false } as never} />)

    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('shows "TLS verification disabled" warning when insecure_skip_tls_verify is true', () => {
    render(<SecuritySection configuration={{ allow_http: false, insecure_skip_tls_verify: true } as never} />)

    expect(screen.getByText('TLS verification disabled')).toBeInTheDocument()
    expect(screen.queryByText('Enabled')).not.toBeInTheDocument()
  })

  it('shows both warnings when both options are enabled', () => {
    render(<SecuritySection configuration={{ allow_http: true, insecure_skip_tls_verify: true } as never} />)

    expect(screen.getByText('HTTP allowed')).toBeInTheDocument()
    expect(screen.getByText('TLS verification disabled')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SecuritySection configuration={{ allow_http: true, insecure_skip_tls_verify: true } as never} />
    )

    const results = await axe(container, { rules: { 'heading-order': { enabled: false } } })
    expect(results).toHaveNoViolations()
  })
})
