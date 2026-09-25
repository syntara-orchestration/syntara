import { beforeEach, describe, expect, it, vi } from 'vitest'

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
    expect(node?.label).toBe('Terraform')
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
})
