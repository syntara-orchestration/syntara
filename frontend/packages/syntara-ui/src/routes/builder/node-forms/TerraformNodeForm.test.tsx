import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RegistryNodeId } from '../../../constants/registryNodeIds'
import { NodeRegistry } from '../registry/NodeRegistry'
import registerTerraformNode from '../registry/nodes/registerTerraformNode'

vi.mock('../components/TFEIntegrationSelector', () => ({
  TFEIntegrationSelector: ({
    onChange,
    onStaleDetected,
    value,
  }: {
    onChange: (id: string | undefined) => void
    onStaleDetected?: () => void
    value?: string
  }) => (
    <div data-testid="tfe-integration-selector">
      <button type="button" onClick={() => onChange('int-tfe-1')}>
        Select TFE integration
      </button>
      <button type="button" onClick={() => onChange(undefined)}>
        Clear TFE integration
      </button>
      <button type="button" onClick={() => onStaleDetected?.()}>
        Fire stale
      </button>
      <span>{value ?? 'none'}</span>
    </div>
  ),
}))
vi.mock('../components/CredentialSelector', () => ({
  CredentialSelector: ({
    label,
    fieldId,
    onChange,
    isDisabled,
  }: {
    label?: string
    fieldId?: string
    onChange?: (id: string | undefined) => void
    isDisabled?: boolean
  }) => (
    <div data-testid={fieldId ?? 'credential-selector'}>
      <span>{label ?? 'Credential'}</span>
      <button type="button" disabled={isDisabled} onClick={() => onChange?.('cred-1')}>
        Select credential
      </button>
    </div>
  ),
}))

const WORKSPACE_ID = 'Workspace ID'
const VARIABLE_ID = 'Variable ID'
const VARIABLE_VALUE = 'Variable value'

function renderVariableStep(subtypeId: string) {
  registerTerraformNode()
  const subtype = NodeRegistry.get(RegistryNodeId.TERRAFORM)?.subtypes?.find((entry) => entry.id === subtypeId)
  if (!subtype?.formComponent) throw new Error('Variable form is not registered')
  const Form = subtype.formComponent
  return render(<Form {...subtype.formProps} onSubmit={vi.fn()} onCancel={vi.fn()} />)
}

describe('Terraform variable step forms', () => {
  it('shows workspace and variable IDs for Delete Variable', async () => {
    const user = userEvent.setup()
    const { container } = renderVariableStep(RegistryNodeId.TFE_DELETE_VARIABLE)
    const workspace = screen.getByRole('textbox', { name: WORKSPACE_ID })
    const variable = screen.getByRole('textbox', { name: VARIABLE_ID })
    await user.type(workspace, 'ws-example')
    await user.type(variable, 'var-example')
    expect(workspace).toHaveValue('ws-example')
    expect(variable).toHaveValue('var-example')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows editable workspace, variable ID, and value for Update Variable', async () => {
    const user = userEvent.setup()
    const { container } = renderVariableStep(RegistryNodeId.TFE_UPDATE_VARIABLE)
    const workspace = screen.getByRole('textbox', { name: WORKSPACE_ID })
    const variable = screen.getByRole('textbox', { name: VARIABLE_ID })
    const value = screen.getByRole('textbox', { name: VARIABLE_VALUE })
    await user.type(workspace, 'ws-example')
    await user.type(variable, 'var-example')
    await user.type(value, 'new value')
    expect(workspace).toHaveValue('ws-example')
    expect(variable).toHaveValue('var-example')
    expect(value).toHaveValue('new value')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('locks plaintext value and shows Secret String selector when Sensitive is enabled', async () => {
    const user = userEvent.setup()
    const { container } = renderVariableStep(RegistryNodeId.TFE_ADD_VARIABLE)
    const value = screen.getByRole('textbox', { name: VARIABLE_VALUE })
    await user.type(value, 'plaintext-secret')
    expect(value).toHaveValue('plaintext-secret')

    await user.click(screen.getByRole('switch', { name: 'Sensitive' }))

    const lockedValue = screen.getByRole('textbox', { name: VARIABLE_VALUE })
    expect(lockedValue).toBeDisabled()
    expect(lockedValue).toHaveValue('')
    expect(screen.getByTestId('tfe-value-credential')).toHaveTextContent('Value credential')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('clears value credential when Sensitive is turned off', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_UPDATE_VARIABLE)

    await user.click(screen.getByRole('switch', { name: 'Sensitive' }))
    expect(screen.getByTestId('tfe-value-credential')).toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Sensitive' }))
    expect(screen.queryByTestId('tfe-value-credential')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: VARIABLE_VALUE })).not.toBeDisabled()
  })
})

describe('Terraform workspace and run step forms', () => {
  it('shows create workspace fields including preset', async () => {
    const { container } = renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByText('Preset')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows agent pool field when agent preset is selected', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)

    await user.click(screen.getByRole('button', { name: /preset/i }))
    await user.click(await screen.findByRole('option', { name: 'Agent execution' }))

    expect(screen.getByRole('textbox', { name: 'Agent pool ID' })).toBeInTheDocument()
  })

  it('shows OAuth VCS fields when remote oauth preset is selected', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)

    await user.click(screen.getByRole('button', { name: /preset/i }))
    await user.click(await screen.findByRole('option', { name: 'Remote + OAuth VCS' }))

    expect(screen.getByRole('textbox', { name: 'Repository name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Branch' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'OAuth token ID' })).toBeInTheDocument()
  })

  it('shows GitHub App fields when remote github preset is selected', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)

    await user.click(screen.getByRole('button', { name: /preset/i }))
    await user.click(await screen.findByRole('option', { name: 'Remote + GitHub' }))

    expect(screen.getByRole('textbox', { name: 'GitHub App installation ID' })).toBeInTheDocument()
  })

  it('shows list workspaces search fields', () => {
    renderVariableStep(RegistryNodeId.TFE_LIST_WORKSPACES)
    expect(screen.getByRole('textbox', { name: 'Organization override' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Search' })).toBeInTheDocument()
  })

  it('shows update workspace fields', () => {
    renderVariableStep(RegistryNodeId.TFE_UPDATE_WORKSPACE)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
    expect(screen.getByText('Preset')).toBeInTheDocument()
  })

  it('shows fetch state outputs workspace field', () => {
    renderVariableStep(RegistryNodeId.TFE_FETCH_STATE_OUTPUTS)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
  })

  it('shows list variables fields', () => {
    renderVariableStep(RegistryNodeId.TFE_LIST_VARIABLES)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Variable key' })).toBeInTheDocument()
  })

  it('shows upload configuration version fields', () => {
    renderVariableStep(RegistryNodeId.TFE_UPLOAD_CONFIGURATION_VERSION)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Artifact (base64 .tar.gz)' })).toBeInTheDocument()
  })

  it('shows trigger run fields', async () => {
    const user = userEvent.setup()
    const { container } = renderVariableStep(RegistryNodeId.TFE_TRIGGER_RUN)
    const workspace = screen.getByRole('textbox', { name: WORKSPACE_ID })
    await user.type(workspace, 'ws-run')
    expect(workspace).toHaveValue('ws-run')
    expect(screen.getByRole('textbox', { name: 'Run mode' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows get run status wait switch', () => {
    renderVariableStep(RegistryNodeId.TFE_GET_RUN_STATUS)
    expect(screen.getByRole('textbox', { name: 'Run ID' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Wait for completion' })).toBeInTheDocument()
  })

  it('shows apply and discard run comment fields', () => {
    renderVariableStep(RegistryNodeId.TFE_APPLY_RUN)
    expect(screen.getByRole('textbox', { name: 'Run ID' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Comment / message' })).toBeInTheDocument()
  })

  it('shows list runs workspace field', () => {
    renderVariableStep(RegistryNodeId.TFE_LIST_RUNS)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
  })

  it('shows link VCS fields', () => {
    renderVariableStep(RegistryNodeId.TFE_LINK_VCS)
    expect(screen.getByRole('textbox', { name: WORKSPACE_ID })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'GitHub installation ID' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Repository name' })).toBeInTheDocument()
  })

  it('shows project management fields', () => {
    renderVariableStep(RegistryNodeId.TFE_CREATE_PROJECT)
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Description' })).toBeInTheDocument()
  })

  it('shows assign team permissions fields', () => {
    renderVariableStep(RegistryNodeId.TFE_ASSIGN_TEAM_PERMISSIONS)
    expect(screen.getByRole('textbox', { name: 'Project ID' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Team ID' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Access/ })).toBeInTheDocument()
  })

  it('shows force delete switch for delete workspace', () => {
    renderVariableStep(RegistryNodeId.TFE_DELETE_WORKSPACE)
    expect(screen.getByRole('switch', { name: 'Force delete' })).toBeInTheDocument()
  })

  it('enables credential selector after integration is chosen and clears on clear', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)

    const credentialButton = screen.getByRole('button', { name: 'Select credential' })
    expect(credentialButton).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Select TFE integration' }))
    expect(credentialButton).toBeEnabled()

    await user.click(screen.getByRole('button', { name: 'Clear TFE integration' }))
    expect(credentialButton).toBeDisabled()
  })

  it('shows stale warning when selected integration is no longer available', async () => {
    const user = userEvent.setup()
    renderVariableStep(RegistryNodeId.TFE_CREATE_WORKSPACE)

    await user.click(screen.getByRole('button', { name: 'Select TFE integration' }))
    await user.click(screen.getByRole('button', { name: 'Fire stale' }))

    expect(screen.getByText(/previously selected TFE integration is no longer available/i)).toBeInTheDocument()
  })
})
