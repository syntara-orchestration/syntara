import type { IntegrationsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { CredentialAffectedResourcesWarnings } from './CredentialAffectedResourcesWarnings'
import { NAMED_DEPENDENCY_LIMIT } from './CredentialDependencySection'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

const mockWorkflows = [
  { id: 'wf-1', name: 'Workflow One' },
  { id: 'wf-2', name: 'Workflow Two' },
]

const mockIntegrations = [
  { id: 'int-1', name: 'GitHub Copilot' },
  { id: 'int-2', name: 'Jira Integration' },
] as Partial<Integration>[] as Integration[]

describe('CredentialAffectedResourcesWarnings', () => {
  it('renders nothing when there are no dependencies and no fetch errors', () => {
    const { container } = render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={[]}
        workflowsFetchError={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('shows a single header and badge rows for workflows and integrations', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={mockWorkflows}
        workflowsFetchError={false}
        affectedIntegrations={mockIntegrations}
        integrationsFetchError={false}
      />
    )

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('Integrations')).toBeInTheDocument()
    expect(screen.queryByText(/will cause these workflows to fail/)).not.toBeInTheDocument()
    expect(screen.queryByText(/will affect these integrations/)).not.toBeInTheDocument()
  })

  it('lists names when a type has 3 or fewer items', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={mockWorkflows}
        workflowsFetchError={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
      />
    )

    expect(screen.getByText('Workflow One')).toBeInTheDocument()
    expect(screen.getByText('Workflow Two')).toBeInTheDocument()
  })

  it('omits name lists when a type has 4 or more items', () => {
    const manyWorkflows = Array.from({ length: NAMED_DEPENDENCY_LIMIT + 1 }, (_, i) => ({
      id: `wf-${i}`,
      name: `Workflow ${i}`,
    }))

    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={manyWorkflows}
        workflowsFetchError={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
      />
    )

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText(String(manyWorkflows.length))).toBeInTheDocument()
    expect(screen.queryByText('Workflow 0')).not.toBeInTheDocument()
  })

  it('shows workflow fetch error alert', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={[]}
        workflowsFetchError={true}
        affectedIntegrations={[]}
        integrationsFetchError={false}
      />
    )

    expect(screen.getByText(/Unable to check which workflows/)).toBeInTheDocument()
    expect(screen.getByText('Proceeding may affect workflows that reference this credential.')).toBeInTheDocument()
    expect(screen.queryByText('Resources that will be affected')).not.toBeInTheDocument()
  })

  it('shows integration fetch error alert', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={[]}
        workflowsFetchError={false}
        affectedIntegrations={[]}
        integrationsFetchError={true}
      />
    )

    expect(screen.getByText(/Unable to check which integrations/)).toBeInTheDocument()
    expect(screen.getByText('Proceeding may affect integrations that reference this credential.')).toBeInTheDocument()
  })

  it('shows integrations section without workflows', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={[]}
        workflowsFetchError={false}
        affectedIntegrations={mockIntegrations}
        integrationsFetchError={false}
      />
    )

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Integrations')).toBeInTheDocument()
    expect(screen.queryByText('Workflows')).not.toBeInTheDocument()
    expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
  })

  it('shows fetch error and dependency summary together', () => {
    render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={mockWorkflows}
        workflowsFetchError={true}
        affectedIntegrations={mockIntegrations}
        integrationsFetchError={true}
      />
    )

    expect(screen.getByText(/Unable to check which workflows/)).toBeInTheDocument()
    expect(screen.getByText(/Unable to check which integrations/)).toBeInTheDocument()
    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Workflow One')).toBeInTheDocument()
    expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <CredentialAffectedResourcesWarnings
        affectedWorkflows={mockWorkflows}
        workflowsFetchError={false}
        affectedIntegrations={mockIntegrations}
        integrationsFetchError={false}
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
