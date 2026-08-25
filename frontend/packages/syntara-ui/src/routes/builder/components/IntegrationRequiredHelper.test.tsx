import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

import { IntegrationRequiredHelper } from './IntegrationRequiredHelper'

vi.mock('../../../components/SynLink', () => ({
  SynLink: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: vi.fn(),
}))

function mockPermissions({ canCreate }: { canCreate: boolean }) {
  vi.mocked(useIntegrationPermissions).mockReturnValue({
    canCreate,
    canUpdate: false,
    canDelete: false,
    isLoading: false,
    tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
  })
}

describe('IntegrationRequiredHelper', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a link when user has create permission', () => {
    mockPermissions({ canCreate: true })
    render(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )

    const link = screen.getByRole('link', { name: 'configure an AAP integration' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/configuration/integrations/configure')
    expect(screen.getByText(/before an integration can be selected/)).toBeInTheDocument()
  })

  it('renders plain text when user lacks create permission', () => {
    mockPermissions({ canCreate: false })
    render(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(/configure an AAP integration/)).toBeInTheDocument()
    expect(screen.getByText(/before an integration can be selected/)).toBeInTheDocument()
  })

  it('renders with custom labels', () => {
    mockPermissions({ canCreate: true })
    render(
      <IntegrationRequiredHelper integrationLabel="a GitHub integration" actionLabel="repositories can be listed" />
    )

    expect(screen.getByText('configure a GitHub integration')).toBeInTheDocument()
    expect(screen.getByText(/before repositories can be listed/)).toBeInTheDocument()
  })

  it('has no accessibility violations with link', async () => {
    mockPermissions({ canCreate: true })
    const { container } = render(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations without link', async () => {
    mockPermissions({ canCreate: false })
    const { container } = render(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders "An administrator must" prefix in both permission states', () => {
    mockPermissions({ canCreate: true })
    const { rerender } = render(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )
    expect(screen.getByText(/An administrator must/)).toBeInTheDocument()

    mockPermissions({ canCreate: false })
    rerender(
      <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
    )
    expect(screen.getByText(/An administrator must/)).toBeInTheDocument()
  })

  it('interpolates integrationLabel into plain text when canCreate is false', () => {
    mockPermissions({ canCreate: false })
    render(<IntegrationRequiredHelper integrationLabel="a custom integration" actionLabel="workflows can run" />)
    expect(screen.getByText(/configure a custom integration/)).toBeInTheDocument()
    expect(screen.getByText(/before workflows can run/)).toBeInTheDocument()
  })
})
