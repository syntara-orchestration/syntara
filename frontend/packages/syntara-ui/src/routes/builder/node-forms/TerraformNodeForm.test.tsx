import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RegistryNodeId } from '../../../constants/registryNodeIds'
import { NodeRegistry } from '../registry/NodeRegistry'
import registerTerraformNode from '../registry/nodes/registerTerraformNode'

vi.mock('../components/TFEIntegrationSelector', () => ({ TFEIntegrationSelector: () => null }))
vi.mock('../components/CredentialSelector', () => ({
  CredentialSelector: ({ label, fieldId }: { label?: string; fieldId?: string }) => (
    <div data-testid={fieldId ?? 'credential-selector'}>{label ?? 'Credential'}</div>
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
})
