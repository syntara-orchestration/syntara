import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ProviderIcon } from './ProviderIcon'

describe('ProviderIcon', () => {
  it('renders Ansible icon for aap idpType', () => {
    render(<ProviderIcon name="My Provider" idpType="aap" />)
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument()
  })

  it('renders globe icon fallback when no idpType is provided', () => {
    render(<ProviderIcon name="Okta SSO" />)
    expect(screen.getByTestId('globe-icon')).toBeInTheDocument()
  })

  it('renders no icon for custom idpType', () => {
    const { container } = render(<ProviderIcon name="Unknown" idpType="custom" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders globe icon for unknown provider', () => {
    render(<ProviderIcon name="custom-idp" />)
    expect(screen.getByTestId('globe-icon')).toBeInTheDocument()
  })

  it('has no accessibility violations with icon', async () => {
    const { container } = render(<ProviderIcon name="My Provider" idpType="aap" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for fallback icon', async () => {
    const { container } = render(<ProviderIcon name="Okta" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when no icon is rendered (custom idpType)', async () => {
    const { container } = render(<ProviderIcon name="Custom" idpType="custom" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
