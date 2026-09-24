import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockAddActivity, mockCreateMcpToolActivity, mockRegister } = vi.hoisted(() => ({
  mockAddActivity: vi.fn(),
  mockCreateMcpToolActivity: vi.fn((options: Record<string, unknown>) => ({
    id: options.id,
    name: options.name,
    type: 'mcp_tool',
    parameters: {
      integration_id: options.integrationId,
      tool_name: options.toolName,
      arguments: options.arguments,
      ...(options.timeoutSeconds !== undefined && { timeout_seconds: options.timeoutSeconds }),
    },
  })),
  mockRegister: vi.fn(),
}))

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: { getState: vi.fn(() => ({ addActivity: mockAddActivity })) },
}))

vi.mock('../../../../stores/workflowFactories', () => ({
  createMcpToolActivity: mockCreateMcpToolActivity,
}))

vi.mock('../../utils/nodeCreationHelpers', () => ({
  buildNamedActivity: vi.fn(
    (baseName: string, requestedName: string | undefined, build: (id: string, name: string) => unknown) => {
      const activityId = 'activity_mcp_tool_1'
      const name = requestedName ?? baseName
      return { activityId, name, activity: build(activityId, name) }
    }
  ),
}))

vi.mock('../helpers/nodeTemplates', () => ({
  createCustomNode: vi.fn((config: Record<string, unknown>, handler: (...args: unknown[]) => void) => ({
    ...config,
    onSubmit: handler,
  })),
}))

vi.mock('../NodeRegistry', () => ({
  NodeRegistry: { register: mockRegister },
}))

import registerMCPToolNode from './registerMCPToolNode'

type RegisteredDefinition = {
  id: string
  label: string
  category: string
  description: string
  keywords: string[]
  formComponent: unknown
  onSubmit: (data: Record<string, unknown>, onSuccess: (id?: string) => void, onError: (error: string) => void) => void
}

function getDefinition(): RegisteredDefinition {
  return mockRegister.mock.calls[0][0] as RegisteredDefinition
}

describe('registerMCPToolNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registerMCPToolNode()
  })

  it('registers under the action category with the expected label', () => {
    const definition = getDefinition()

    expect(definition.id).toBe('action-mcp-tool')
    expect(definition.label).toBe('MCP tool')
    expect(definition.category).toBe('action')
    expect(definition.keywords).toContain('mcp')
    expect(definition.formComponent).toBeDefined()
  })

  it('saves parameters as integration_id, tool_name, arguments and timeout_seconds', () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()

    getDefinition().onSubmit(
      {
        name: 'List directory',
        integration_id: 'integration-1',
        tool_name: 'list_directory',
        argumentsJson: '{"path": "/tmp"}',
        timeout_seconds: 30,
      },
      onSuccess,
      onError
    )

    expect(mockCreateMcpToolActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        integrationId: 'integration-1',
        toolName: 'list_directory',
        arguments: { path: '/tmp' },
        timeoutSeconds: 30,
      })
    )
    expect(mockAddActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'mcp_tool',
        parameters: expect.objectContaining({
          integration_id: 'integration-1',
          tool_name: 'list_directory',
          arguments: { path: '/tmp' },
          timeout_seconds: 30,
        }) as Record<string, unknown>,
      })
    )
    expect(onSuccess).toHaveBeenCalledWith('activity_mcp_tool_1')
    expect(onError).not.toHaveBeenCalled()
  })

  it('defaults arguments to an empty object when the editor is blank', () => {
    getDefinition().onSubmit(
      { name: 'No args', integration_id: 'integration-1', tool_name: 'ping', argumentsJson: '' },
      vi.fn(),
      vi.fn()
    )

    expect(mockCreateMcpToolActivity).toHaveBeenCalledWith(expect.objectContaining({ arguments: {} }))
  })

  it('rejects arguments that are not a JSON object', () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()

    getDefinition().onSubmit(
      { name: 'Bad args', integration_id: 'integration-1', tool_name: 'ping', argumentsJson: '[1, 2]' },
      onSuccess,
      onError
    )

    expect(onError).toHaveBeenCalledWith('Arguments must be a JSON object')
    expect(mockAddActivity).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
