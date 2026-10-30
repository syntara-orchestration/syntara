import type { WorkflowAPI } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../client'

import { resolveWorkflowListRunTrigger, resolveWorkflowRunTrigger } from './resolveWorkflowRunTrigger'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

vi.mock('../../client', () => ({
  workflowFetchClient: {
    GET: vi.fn(),
  },
}))

function mockWorkflow(overrides: Partial<Workflow> = {}): Workflow {
  return {
    id: 'wf-1',
    name: 'Test Workflow',
    description: null,
    labels: {},
    current_version: 2,
    is_builtin: false,
    is_enabled: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: { id: 'u-1', name: 'test-user', type: 'user' },
    project_id: 'proj-1',
    published_version_id: 'pub-1',
    published_version_number: 1,
    ...overrides,
  }
}

function mockGetResponse(data: Record<string, unknown> | undefined, error?: Record<string, unknown>) {
  return { data, error, response: new Response() } as never
}

describe('resolveWorkflowRunTrigger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when workflow has no id', async () => {
    await expect(resolveWorkflowRunTrigger(mockWorkflow({ id: undefined as unknown as string }))).resolves.toBeNull()
    expect(workflowFetchClient.GET).not.toHaveBeenCalled()
  })

  it('returns null when workflow fetch fails', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(mockGetResponse(undefined, { detail: 'not found' }))

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).resolves.toBeNull()
  })

  it('returns the first trigger from the current version when it matches published', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'trigger-1',
                name: 'Manual Trigger',
                parameters: {
                  input_schema: { type: 'object', properties: { version: { type: 'string' } } },
                },
              },
            ],
          },
        },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow({ published_version_number: 1 }))).resolves.toEqual({
      triggerNodeId: 'trigger-1',
      triggerName: 'Manual Trigger',
      triggerType: undefined,
      inputSchema: { type: 'object', properties: { version: { type: 'string' } } },
      hasTriggerReferences: false,
      formTrigger: undefined,
    })
    expect(workflowFetchClient.GET).toHaveBeenCalledTimes(1)
  })

  it('fetches the published version when it differs from the current draft', async () => {
    vi.mocked(workflowFetchClient.GET).mockImplementation((path: string) => {
      if (path === '/workflows/{workflow_id}/versions/{version}') {
        return Promise.resolve(
          mockGetResponse({
            workflow_definition: {
              triggers: [
                {
                  id: 'published-trigger',
                  name: 'Published Trigger',
                  parameters: { input_schema: { type: 'object', properties: { env: { type: 'string' } } } },
                },
              ],
            },
          })
        )
      }
      return Promise.resolve(
        mockGetResponse({
          id: 'wf-1',
          current_version: 2,
          published_version_number: 1,
          version: {
            workflow_definition: {
              triggers: [{ id: 'draft-trigger', name: 'Draft Trigger', parameters: {} }],
            },
          },
        })
      )
    })

    await expect(resolveWorkflowRunTrigger(mockWorkflow({ published_version_number: 1 }))).resolves.toEqual({
      triggerNodeId: 'published-trigger',
      triggerName: 'Published Trigger',
      triggerType: undefined,
      inputSchema: { type: 'object', properties: { env: { type: 'string' } } },
      hasTriggerReferences: false,
      formTrigger: undefined,
    })
    expect(workflowFetchClient.GET).toHaveBeenCalledWith('/workflows/{workflow_id}/versions/{version}', {
      params: { path: { workflow_id: 'wf-1', version: 1 } },
    })
  })

  it('returns null when the workflow has no triggers', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: { workflow_definition: { triggers: [] } },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).resolves.toBeNull()
  })

  it('falls back to Trigger name when trigger name is missing', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [{ id: 'trigger-1', parameters: {} }],
          },
        },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).resolves.toEqual({
      triggerNodeId: 'trigger-1',
      triggerName: 'Trigger',
      triggerType: undefined,
      inputSchema: undefined,
      hasTriggerReferences: false,
      formTrigger: undefined,
    })
  })

  it('throws when published version fetch fails while draft differs', async () => {
    vi.mocked(workflowFetchClient.GET).mockImplementation((path: string) => {
      if (path === '/workflows/{workflow_id}/versions/{version}') {
        return Promise.resolve(mockGetResponse(undefined, { detail: 'not found' }))
      }
      return Promise.resolve(
        mockGetResponse({
          id: 'wf-1',
          current_version: 2,
          published_version_number: 1,
          version: {
            workflow_definition: {
              triggers: [{ id: 'draft-trigger', name: 'Draft Trigger', parameters: {} }],
            },
          },
        })
      )
    })

    await expect(resolveWorkflowRunTrigger(mockWorkflow({ published_version_number: 1 }))).rejects.toThrow(
      /published workflow version/i
    )
  })

  it('ignores non-object triggers and non-object input_schema values', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              'not-a-trigger',
              { id: 'trigger-1', name: 'Manual Trigger', parameters: { input_schema: 'bad' } },
            ],
          },
        },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).resolves.toEqual({
      triggerNodeId: 'trigger-1',
      triggerName: 'Manual Trigger',
      triggerType: undefined,
      inputSchema: undefined,
      hasTriggerReferences: false,
      formTrigger: undefined,
    })
  })

  it('prefers a form trigger over an earlier manual trigger', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'manual-1',
                name: 'Manual',
                type: 'manual_trigger',
                parameters: { input_schema: { type: 'object', properties: { version: { type: 'string' } } } },
              },
              {
                id: 'form-1',
                name: 'Intake',
                type: 'form_trigger',
                parameters: {
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'reason', label: 'Reason', required: true }],
                  },
                },
              },
            ],
          },
        },
      })
    )

    const result = await resolveWorkflowRunTrigger(mockWorkflow())
    expect(result?.triggerNodeId).toBe('form-1')
    expect(result?.triggerType).toBe('form_trigger')
  })

  it('returns chooseFormStep when multiple form steps require input', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'form-a',
                name: 'Alpha',
                type: 'form_trigger',
                parameters: {
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }],
                  },
                },
              },
              {
                id: 'form-b',
                name: 'Beta',
                type: 'form_trigger',
                parameters: {
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'b', label: 'B', required: true }],
                  },
                },
              },
            ],
          },
        },
      })
    )

    await expect(resolveWorkflowListRunTrigger(mockWorkflow())).resolves.toEqual({
      kind: 'chooseFormStep',
      triggers: [
        expect.objectContaining({ triggerNodeId: 'form-a', triggerName: 'Alpha' }),
        expect.objectContaining({ triggerNodeId: 'form-b', triggerName: 'Beta' }),
      ],
    })
  })

  it('throws when resolveWorkflowRunTrigger is used for multiple form steps', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'form-a',
                name: 'Alpha',
                type: 'form_trigger',
                parameters: {
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }],
                  },
                },
              },
              {
                id: 'form-b',
                name: 'Beta',
                type: 'form_trigger',
                parameters: {
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'b', label: 'B', required: true }],
                  },
                },
              },
            ],
          },
        },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).rejects.toThrow(/multiple form steps/i)
  })

  it('parses form trigger presentation from parameters', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'form-1',
                name: 'Intake',
                type: 'form_trigger',
                parameters: {
                  message: 'Please complete the form',
                  submit_label: 'Send',
                  success_message: 'Thanks!',
                  form_definition: {
                    fields: [{ type: 'text', value_name: 'reason', label: 'Reason', required: true }],
                  },
                },
              },
            ],
          },
        },
      })
    )

    const result = await resolveWorkflowRunTrigger(mockWorkflow())
    expect(result?.triggerType).toBe('form_trigger')
    expect(result?.formTrigger?.message).toBe('Please complete the form')
    expect(result?.formTrigger?.submitLabel).toBe('Send')
    expect(result?.formTrigger?.definition.fields).toHaveLength(1)
  })

  it('returns null when workflow definition has no triggers array', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: { workflow_definition: { nodes: [] } },
      })
    )

    await expect(resolveWorkflowRunTrigger(mockWorkflow())).resolves.toBeNull()
  })
})
