import type { IntegrationsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { Credential } from './credentialConstants'
import { DeleteCredentialDialog } from './DeleteCredentialDialog'
import { DisableCredentialDialog } from './DisableCredentialDialog'

const mockCredential: Credential = {
  id: '1',
  name: 'Test Credential',
  description: 'Test description',
  credential_type_id: 'type-1',
  inputs: {},
  enabled: true,
  labels: {},
  created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-1' },
  project_id: 'proj-1',
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

const mockAffectedWorkflows = [
  { id: 'wf-1', name: 'Workflow One' },
  { id: 'wf-2', name: 'Workflow Two' },
]

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

const mockAffectedIntegrations = [
  { id: 'int-1', name: 'GitHub Copilot' },
  { id: 'int-2', name: 'Jira Integration' },
] as Partial<Integration>[] as Integration[]

describe('DisableCredentialDialog', () => {
  it('returns null when credential is null', () => {
    const { container } = render(
      <DisableCredentialDialog
        credential={null}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders dialog with credential name', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText('Disable credential?')).toBeInTheDocument()
    expect(screen.getByText('Test Credential')).toBeInTheDocument()
  })

  it('shows affected workflows list and re-enable message together', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={mockAffectedWorkflows}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Workflow One')).toBeInTheDocument()
    expect(screen.getByText('Workflow Two')).toBeInTheDocument()
    expect(screen.queryByText(/will cause these workflows to fail/)).not.toBeInTheDocument()
    expect(screen.getByText(/You can re-enable/)).toBeInTheDocument()
  })

  it('shows badge count when only one workflow affected', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[mockAffectedWorkflows[0]]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows warning when workflowsFetchError is true', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={true}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/Unable to check/)).toBeInTheDocument()
  })

  it('hides re-enable message when workflowsFetchError is true', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={true}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.queryByText(/You can re-enable/)).not.toBeInTheDocument()
  })

  it('shows both error and workflows when workflowsFetchError and workflows are present', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={mockAffectedWorkflows}
        workflowsFetchError={true}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/Unable to check/)).toBeInTheDocument()
    expect(screen.getByText('Workflow One')).toBeInTheDocument()
    expect(screen.queryByText(/You can re-enable/)).not.toBeInTheDocument()
  })

  it('disables buttons while isLoading is true', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        isLoading={true}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /Disable/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('enables buttons when isLoading is false', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        isLoading={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Disable' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('does not show affected workflows list when no workflows affected', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.queryByText('Workflows')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows re-enable message', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/You can re-enable the credential at any time/)).toBeInTheDocument()
  })

  it('calls onConfirm when Disable button clicked', async () => {
    const user = userEvent.setup()
    const mockOnConfirm = vi.fn()

    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={mockOnConfirm}
        onClose={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Disable' }))
    expect(mockOnConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Cancel button clicked', async () => {
    const user = userEvent.setup()
    const mockOnClose = vi.fn()

    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={mockAffectedWorkflows}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with workflow fetch error', async () => {
    const { container } = render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={true}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows loading spinner when checking workflows', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={true}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/Checking for workflows/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Disable/i })).toBeDisabled()
  })

  it('disables Disable button when both isLoading and isLoadingWorkflows are true', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={true}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        isLoading={true}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /Disable/i })).toBeDisabled()
  })

  it('enables Disable button when isLoading is explicitly false and not loading workflows', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        isLoading={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Disable' })).toBeEnabled()
  })

  it('shows affected integrations list when integrations are affected', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={mockAffectedIntegrations}
        integrationsFetchError={false}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText('Integrations')).toBeInTheDocument()
    expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
    expect(screen.getByText('Jira Integration')).toBeInTheDocument()
  })

  it('shows loading spinner when checking integrations', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={false}
        isLoadingIntegrations={true}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/Checking for workflows and integrations/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Disable/i })).toBeDisabled()
  })

  it('hides re-enable message when integrationsFetchError is true', () => {
    render(
      <DisableCredentialDialog
        credential={mockCredential}
        affectedWorkflows={[]}
        workflowsFetchError={false}
        isLoadingWorkflows={false}
        affectedIntegrations={[]}
        integrationsFetchError={true}
        isLoadingIntegrations={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/Unable to check which integrations/)).toBeInTheDocument()
    expect(screen.queryByText(/You can re-enable/)).not.toBeInTheDocument()
  })
})

describe('DeleteCredentialDialog', () => {
  const defaultDeleteProps = {
    affectedWorkflows: [] as { id: string; name: string }[],
    workflowsFetchError: false,
    isLoadingWorkflows: false,
    affectedIntegrations: [],
    integrationsFetchError: false,
    isLoadingIntegrations: false,
    onConfirm: vi.fn(),
    onClose: vi.fn(),
  }

  it('returns null when credential is null', () => {
    const { container } = render(<DeleteCredentialDialog credential={null} {...defaultDeleteProps} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders dialog with credential name when no workflows reference it', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} />)

    expect(screen.getByText('Delete credential?')).toBeInTheDocument()
    expect(screen.getByText(/Test Credential/)).toBeInTheDocument()
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument()
  })

  it('warns but allows deletion when workflows reference the credential', async () => {
    const user = userEvent.setup()
    const workflows = [
      { id: 'wf-1', name: 'Deploy Pipeline' },
      { id: 'wf-2', name: 'Health Check' },
    ]
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} affectedWorkflows={workflows} />)

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.queryByText(/will cause these workflows to fail/)).not.toBeInTheDocument()
    expect(screen.getByText('Deploy Pipeline')).toBeInTheDocument()
    expect(screen.getByText('Health Check')).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', {
        name: 'I understand this credential and the resources shown above will be affected by this deletion.',
      })
    ).toBeInTheDocument()
    // Delete button is disabled until checkbox is checked
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
  })

  it('uses compact dependency summary without names when 4 or more of each type', () => {
    const workflows = Array.from({ length: 12 }, (_, i) => ({ id: `wf-${i}`, name: `Workflow ${i}` }))
    const integrations = Array.from({ length: 12 }, (_, i) => ({
      id: `int-${i}`,
      name: `Integration ${i}`,
    })) as Partial<Integration>[] as Integration[]

    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        affectedWorkflows={workflows}
        affectedIntegrations={integrations}
      />
    )

    expect(screen.getByText('Resources that will be affected')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('Integrations')).toBeInTheDocument()
    expect(screen.getAllByText('12')).toHaveLength(2)
    expect(screen.queryByText('Workflow 0')).not.toBeInTheDocument()
    expect(screen.queryByText('Integration 0')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('calls onConfirm when Delete button clicked', async () => {
    const user = userEvent.setup()
    const mockOnConfirm = vi.fn()

    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} onConfirm={mockOnConfirm} />)

    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(mockOnConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Cancel button clicked', async () => {
    const user = userEvent.setup()
    const mockOnClose = vi.fn()

    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} onClose={mockOnClose} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('shows loading spinner when checking workflows', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} isLoadingWorkflows={true} />)

    expect(screen.getByText(/Checking for workflows/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
  })

  it('disables Delete button when checking integrations', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} isLoadingIntegrations={true} />)

    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
  })

  it('disables Delete button when isLoading is true and isLoadingWorkflows is false', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        isLoading={true}
        isLoadingWorkflows={false}
      />
    )

    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
  })

  it('shows warning when workflowsFetchError is true', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} workflowsFetchError={true} />)

    expect(screen.getByText(/Unable to check which workflows/)).toBeInTheDocument()
  })

  it('shows badge count when only one workflow affected', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        affectedWorkflows={[{ id: 'wf-1', name: 'Solo Workflow' }]}
      />
    )

    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('enables buttons when neither loading workflows nor deleting', async () => {
    const user = userEvent.setup()
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} />)

    // Delete button is disabled until checkbox is checked
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()

    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('shows both error and workflow list when workflowsFetchError and workflows are present', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        workflowsFetchError={true}
        affectedWorkflows={[{ id: 'wf-1', name: 'Stale Workflow' }]}
      />
    )

    expect(screen.getByText(/Unable to check/)).toBeInTheDocument()
    expect(screen.getByText('Stale Workflow')).toBeInTheDocument()
  })

  it('disables buttons while isLoading is true', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} isLoading={true} />)

    // PF6 loading button prepends spinner to accessible name
    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with affected workflows', async () => {
    const workflows = [
      { id: 'wf-1', name: 'Deploy Pipeline' },
      { id: 'wf-2', name: 'Health Check' },
    ]
    const { container } = render(
      <DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} affectedWorkflows={workflows} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with workflow fetch error', async () => {
    const { container } = render(
      <DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} workflowsFetchError={true} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('disables Delete button when isLoading is true but isLoadingWorkflows is false', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        isLoading={true}
        isLoadingWorkflows={false}
      />
    )

    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('disables Delete button when both isLoading and isLoadingWorkflows are true', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        isLoading={true}
        isLoadingWorkflows={true}
      />
    )

    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled()
  })

  it('shows acknowledgement checkbox text without dependencies', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} />)

    expect(
      screen.getByRole('checkbox', { name: 'I understand this credential will be permanently deleted.' })
    ).toBeInTheDocument()
  })

  it('blocks deletion and disables confirm when integrations reference the credential', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        affectedIntegrations={mockAffectedIntegrations}
      />
    )

    // The backend rejects the delete outright while any integration references the
    // credential — there's nothing to acknowledge, so no checkbox is shown, and the
    // confirm action stays disabled instead of inviting a doomed confirmation.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Detach integrations first' })).toBeDisabled()
    expect(screen.getByText(/can.t be deleted while it.s still used by the integration\(s\) below/)).toBeInTheDocument()
    expect(
      screen.getByText("This credential can't be deleted until it's detached from these integrations")
    ).toBeInTheDocument()
  })

  it('keeps confirm disabled for blocking integrations even when workflows also reference the credential', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        affectedWorkflows={[{ id: 'wf-1', name: 'Deploy Pipeline' }]}
        affectedIntegrations={mockAffectedIntegrations}
      />
    )

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Detach integrations first' })).toBeDisabled()
  })

  it('enables Delete button (after checkbox) when both isLoading and isLoadingWorkflows are explicitly false', async () => {
    const user = userEvent.setup()
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        isLoading={false}
        isLoadingWorkflows={false}
      />
    )

    // Delete button is disabled until checkbox is checked
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('shows affected integrations list when integrations are affected', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        affectedIntegrations={mockAffectedIntegrations}
      />
    )

    expect(screen.getByText('Integrations')).toBeInTheDocument()
    expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
    expect(screen.getByText('Jira Integration')).toBeInTheDocument()
  })

  it('shows warning when integrationsFetchError is true', () => {
    render(<DeleteCredentialDialog credential={mockCredential} {...defaultDeleteProps} integrationsFetchError={true} />)

    expect(screen.getByText(/Unable to check which integrations/)).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'I understand this credential will be permanently deleted.' })
    ).toBeInTheDocument()
  })

  it('shows loading spinner when checking integrations only', () => {
    render(
      <DeleteCredentialDialog
        credential={mockCredential}
        {...defaultDeleteProps}
        isLoadingWorkflows={false}
        isLoadingIntegrations={true}
      />
    )

    expect(screen.getByText(/Checking for workflows and integrations/)).toBeInTheDocument()
  })
})
