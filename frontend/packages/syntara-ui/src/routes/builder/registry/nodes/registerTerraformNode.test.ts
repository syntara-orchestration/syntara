import { beforeEach, describe, expect, it, vi } from 'vitest'

import TerraformIcon from '../../../../assets/terraform.svg?react'
import { RegistryNodeId } from '../../../../constants'
import { NodeRegistry } from '../NodeRegistry'

import registerTerraformNode from './registerTerraformNode'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: () => ({
      addActivity: vi.fn(),
    }),
  },
}))

describe('registerTerraformNode', () => {
  beforeEach(() => {
    NodeRegistry.clear()
    registerTerraformNode()
  })

  it('registers the Terraform category with workspace subtypes', () => {
    const node = NodeRegistry.get(RegistryNodeId.TERRAFORM)
    expect(node).toBeDefined()
    expect(node?.label).toBe('Terraform Enterprise')
    expect(node?.icon).toBe(TerraformIcon)
    expect(node?.subtypes?.every((subtype) => subtype.icon === TerraformIcon)).toBe(true)
    expect(node?.subtypes?.length).toBeGreaterThanOrEqual(5)
    const createWs = node?.subtypes?.find((s) => s.id === RegistryNodeId.TFE_CREATE_WORKSPACE)
    expect(createWs?.label).toBe('Create Workspace')
  })

  it('onSubmit creates an activity for create workspace', () => {
    const node = NodeRegistry.get(RegistryNodeId.TERRAFORM)
    const onSuccess = vi.fn()
    const onError = vi.fn()
    node?.onSubmit(
      {
        name: 'Create WS',
        integration_id: '11111111-1111-1111-1111-111111111111',
        credential_id: '22222222-2222-2222-2222-222222222222',
        name_field: 'my-ws',
      },
      onSuccess,
      onError,
      RegistryNodeId.TFE_CREATE_WORKSPACE
    )
    expect(onError).not.toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalled()
  })

  it('onSubmit reports an error for an unknown subtype', () => {
    const node = NodeRegistry.get(RegistryNodeId.TERRAFORM)
    const onSuccess = vi.fn()
    const onError = vi.fn()
    node?.onSubmit({ name: 'Bad' }, onSuccess, onError, 'tfe-unknown-step')
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith('Unknown Terraform step type')
  })

  it('onSubmit reports an error when subtypeId is missing', () => {
    const node = NodeRegistry.get(RegistryNodeId.TERRAFORM)
    const onSuccess = vi.fn()
    const onError = vi.fn()
    node?.onSubmit({ name: 'Bad' }, onSuccess, onError)
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith('Unknown Terraform step type')
  })

  it('registers variable and run subtypes', () => {
    const node = NodeRegistry.get(RegistryNodeId.TERRAFORM)
    const ids = new Set(node?.subtypes?.map((s) => s.id))
    expect(ids.has(RegistryNodeId.TFE_ADD_VARIABLE)).toBe(true)
    expect(ids.has(RegistryNodeId.TFE_TRIGGER_RUN)).toBe(true)
    expect(ids.has(RegistryNodeId.TFE_ASSIGN_TEAM_PERMISSIONS)).toBe(true)
  })
})
