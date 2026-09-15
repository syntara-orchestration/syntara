import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerAAPNode from './registerAAPNode'

// Mock the store
vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addActivity: vi.fn(),
    })),
  },
  createAAPJobTemplateActivity: vi.fn(
    (id: string, name: string, templateId: number, parameters: Record<string, unknown>) => ({
      id,
      name,
      type: 'aap_job_template' as const,
      parameters: { job_template_id: templateId, ...parameters },
    })
  ),
  createAAPWorkflowTemplateActivity: vi.fn(
    (id: string, name: string, workflowTemplateId: number, parameters: Record<string, unknown>) => ({
      id,
      name,
      type: 'aap_workflow_job_template' as const,
      parameters: { workflow_job_template_id: workflowTemplateId, ...parameters },
    })
  ),
}))

describe('registerAAPNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Unregister AAP node if it exists from previous test
    NodeRegistry.unregister(RegistryNodeId.AAP_EXECUTION)
  })

  it('registers AAP Execution category node in the NodeRegistry', () => {
    registerAAPNode()

    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryNodeId.AAP_EXECUTION)
    expect(registration?.label).toBe('AAP Execution')
    expect(registration?.category).toBe('action')
    expect(registration?.description).toBe('Execute Ansible Automation Platform jobs and workflows')
  })

  it('registers with correct keywords for searchability', () => {
    registerAAPNode()

    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    expect(registration?.keywords).toEqual(
      expect.arrayContaining(['ansible', 'aap', 'workflow', 'playbook', 'job', 'template'])
    )
  })

  it('includes two subtypes: job template and workflow template', () => {
    registerAAPNode()

    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    expect(registration?.subtypes).toBeDefined()
    expect(registration?.subtypes).toHaveLength(2)

    const jobTemplateSubtype = registration?.subtypes?.find((s) => s.id === RegistryNodeId.AAP_JOB_TEMPLATE)
    expect(jobTemplateSubtype).toBeDefined()
    expect(jobTemplateSubtype?.label).toBe('Launch AAP job template')
    expect(jobTemplateSubtype?.formComponent).toBeDefined()

    const workflowTemplateSubtype = registration?.subtypes?.find((s) => s.id === RegistryNodeId.AAP_WORKFLOW_TEMPLATE)
    expect(workflowTemplateSubtype).toBeDefined()
    expect(workflowTemplateSubtype?.label).toBe('Launch AAP workflow template')
    expect(workflowTemplateSubtype?.formComponent).toBeDefined()
  })

  it('includes onSubmit handler', () => {
    registerAAPNode()

    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    expect(registration?.onSubmit).toBeDefined()
  })

  it('onSubmit creates job template activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Job',
      organization_name: 'Default',
      job_template_name: 'Deploy App',
      job_template_id: 123,
      inventory_id: 456,
      extra_vars: '{"key": "value"}',
    }

    registration?.onSubmit(formData, onSuccess, onError, RegistryNodeId.AAP_JOB_TEMPLATE)

    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
    expect(mockAddActivity).toHaveBeenCalled()
  })

  it('onSubmit creates workflow template activity and calls onSuccess', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Workflow',
      organization_name: 'Default',
      workflow_job_template_name: 'Deploy Workflow',
      workflow_job_template_id: 456,
      extra_vars: '{"key": "value"}',
    }

    registration?.onSubmit(formData, onSuccess, onError, RegistryNodeId.AAP_WORKFLOW_TEMPLATE)

    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
    expect(mockAddActivity).toHaveBeenCalled()
  })

  it('creates expression-mode activity when use_input_variables is true without a job template', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Test AAP Job',
        use_input_variables: true,
        organization_name: '',
        job_template_name: '',
        job_template_id: undefined,
      },
      onSuccess,
      onError,
      RegistryNodeId.AAP_JOB_TEMPLATE
    )

    expect(onError).not.toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(mockAddActivity).toHaveBeenCalled()
    const activity = mockAddActivity.mock.calls[0]?.[0] as { parameters?: Record<string, unknown> }
    expect(activity.parameters).not.toHaveProperty('job_template_id')
  })

  it('creates activity even when job_template_id is undefined', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Job',
      organization_name: 'Default',
      job_template_name: 'Deploy App',
      job_template_id: undefined,
    }

    registration?.onSubmit(formData, onSuccess, onError, RegistryNodeId.AAP_JOB_TEMPLATE)

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('creates activity even when workflow_job_template_id is undefined', () => {
    const mockAddActivity = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Workflow',
      organization_name: 'Default',
      workflow_job_template_name: 'Deploy Workflow',
      workflow_job_template_id: undefined,
    }

    registration?.onSubmit(formData, onSuccess, onError, RegistryNodeId.AAP_WORKFLOW_TEMPLATE)

    expect(mockAddActivity).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit calls onError when subtypeId is missing', () => {
    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Job',
      organization_name: 'Default',
      job_template_name: 'Deploy App',
      job_template_id: 123,
    }

    // No subtypeId provided
    registration?.onSubmit(formData, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Invalid AAP execution type')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles errors and calls onError with message', () => {
    // Mock addActivity to throw
    const mockAddActivity = vi.fn(() => {
      throw new Error('Store error')
    })
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addActivity: mockAddActivity,
    } as never)

    registerAAPNode()
    const registration = NodeRegistry.get(RegistryNodeId.AAP_EXECUTION)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const formData = {
      name: 'Test AAP Job',
      organization_name: 'Default',
      job_template_name: 'Deploy App',
      job_template_id: 123,
    }

    registration?.onSubmit(formData, onSuccess, onError, RegistryNodeId.AAP_JOB_TEMPLATE)

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
