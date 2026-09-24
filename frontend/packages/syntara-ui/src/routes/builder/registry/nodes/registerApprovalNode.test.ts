import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerApprovalNode from './registerApprovalNode'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createApprovalActivity: vi.fn((opts: Record<string, unknown>) => ({
    id: opts.id,
    name: opts.name,
    type: 'approval' as const,
  })),
}))

describe('registerApprovalNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(RegistryNodeId.APPROVAL)
  })

  it('registers the Approval step type in the NodeRegistry', () => {
    registerApprovalNode()

    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryNodeId.APPROVAL)
    expect(registration?.label).toBe('Approval')
    expect(registration?.category).toBe('human_tasks')
    expect(registration?.description).toBe('Wait for approval or human input before continuing')
  })

  it('registers with enabled=false (add panel uses Human tasks parent)', () => {
    registerApprovalNode()

    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    expect(registration?.enabled).toBe(false)
  })

  it('registers with correct order', () => {
    registerApprovalNode()

    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    expect(registration?.order).toBe(50)
  })

  it('registers with searchable keywords', () => {
    registerApprovalNode()

    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    expect(registration?.keywords).toEqual(
      expect.arrayContaining(['approve', 'approval', 'review', 'manual', 'gate', 'checkpoint'])
    )
  })

  it('onSubmit creates an approval activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerApprovalNode()
    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Manager Approval',
      approvers: ['user1', 'user2'],
      prompt: 'Please review this deployment',
      timeout: 3600,
      onTimeout: 'reject' as const,
    }

    registration?.onSubmit(formData, onSuccess, onError)

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit handles thrown errors and calls onError', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw new Error('Store error')
      }),
    } as never)

    registerApprovalNode()
    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Test', approvers: [], prompt: '', timeout: 0, onTimeout: 'reject' as const },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles non-Error throws with generic message', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: vi.fn(() => {
        throw Object.create(null) as Error
      }),
    } as never)

    registerApprovalNode()
    const registration = NodeRegistry.get(RegistryNodeId.APPROVAL)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'Test', approvers: [], prompt: '', timeout: 0, onTimeout: 'reject' as const },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Failed to add approval step')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
