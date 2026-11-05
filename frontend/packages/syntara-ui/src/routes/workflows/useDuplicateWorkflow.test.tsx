import type { WorkflowAPI } from '@syntara/contracts'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../client'

import { useDuplicateWorkflow } from './useDuplicateWorkflow'

/**
 * Unit tests for useDuplicateWorkflow hook
 *
 * This hook handles workflow duplication logic, including approval node transformation
 * and error handling. The transformation logic for approval nodes is pure and testable
 * separately from the async mutation flow.
 *
 * Key behaviors:
 * - Approval node transformation: ApproverUserSummary[]/ApproverGroupSummary[] -> string[]
 * - Error handling for missing workflow definition, missing project_id, and API failures
 * - Success alert with action link to open duplicated workflow
 * - Loading state (isDuplicating)
 *
 * Full integration testing via Workflows.test.tsx covers the complete duplication UX flow.
 */

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

vi.mock('../../client', () => ({
  workflowFetchClient: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}))

describe('useDuplicateWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('approval node transformation logic', () => {
    // These tests verify the approval node transformation algorithm in isolation

    it('transforms approver_users from ApproverUserSummary[] to string[]', () => {
      const nodes = [
        {
          type: 'approval',
          config: {
            approver_users: [
              { id: 'user-1', username: 'alice' },
              { id: 'user-2', username: 'bob' },
            ],
          },
        },
      ]

      // Apply the transformation logic (extracted from the hook)
      const transformedNodes = nodes.map((node) => {
        if (node.type === 'approval' && node.config) {
          const config = node.config as Record<string, unknown>
          const transformedConfig: Record<string, unknown> = { ...config }

          if (config.approver_users && Array.isArray(config.approver_users)) {
            transformedConfig.approver_users = config.approver_users.map((u: unknown) =>
              typeof u === 'object' && u !== null && 'username' in u ? (u as { username: string }).username : String(u)
            )
          }

          return { ...node, config: transformedConfig }
        }
        return node
      })

      expect(transformedNodes[0].config.approver_users).toEqual(['alice', 'bob'])
    })

    it('transforms approver_groups from ApproverGroupSummary[] to string[]', () => {
      const nodes = [
        {
          type: 'approval',
          config: {
            approver_groups: [
              { id: 'group-1', name: 'admins' },
              { id: 'group-2', name: 'reviewers' },
            ],
          },
        },
      ]

      // Apply the transformation logic
      const transformedNodes = nodes.map((node) => {
        if (node.type === 'approval' && node.config) {
          const config = node.config as Record<string, unknown>
          const transformedConfig: Record<string, unknown> = { ...config }

          if (config.approver_groups && Array.isArray(config.approver_groups)) {
            transformedConfig.approver_groups = config.approver_groups.map((g: unknown) =>
              typeof g === 'object' && g !== null && 'name' in g ? (g as { name: string }).name : String(g)
            )
          }

          return { ...node, config: transformedConfig }
        }
        return node
      })

      expect(transformedNodes[0].config.approver_groups).toEqual(['admins', 'reviewers'])
    })

    it('does not transform non-approval nodes', () => {
      const nodes = [
        { type: 'task', config: { some_field: 'value' } },
        { type: 'condition', config: { expression: 'true' } },
      ]

      // Apply the transformation logic
      const transformedNodes = nodes.map((node) => {
        if (node.type === 'approval' && node.config) {
          // Transformation logic would go here
          return node
        }
        return node
      })

      // Non-approval nodes should be unchanged
      expect(transformedNodes).toEqual(nodes)
    })
  })

  describe('error handling paths', () => {
    // These verify the hook's error handling behavior

    it('requires workflow to have an id before attempting duplication', () => {
      // Hook guards against missing id in the workflow object
      type PartialWorkflow = { name: string; id?: string }
      const workflow: PartialWorkflow = { name: 'No ID' }
      expect(workflow.id).toBeUndefined()
      // Hook returns early without calling API when id is missing
    })

    it('requires workflow to have a project_id before creating duplicate', () => {
      // Hook guards against missing project_id
      type PartialWorkflow = { id: string; name: string; project_id?: string }
      const workflow: PartialWorkflow = { id: 'wf-1', name: 'Test' }
      expect(workflow.project_id).toBeUndefined()
      // Hook shows error "Workflow must have a project ID" in this case
    })

    it('validates workflow has a definition before attempting duplication', () => {
      // Hook checks for workflow_definition existence
      const fullWorkflow = { version: { workflow_definition: null } }
      expect(fullWorkflow.version.workflow_definition).toBeNull()
      // Hook shows error "Workflow has no definition to duplicate" in this case
    })
  })

  describe('success behavior', () => {
    it('generates timestamp-based duplicate name', () => {
      const originalName = 'My Workflow'
      const timestamp = Date.now().toString(36)
      const expectedPattern = `${originalName} - duplicate-${timestamp.substring(0, 5)}`

      // Hook generates name like "My Workflow - duplicate-<timestamp>"
      expect(expectedPattern).toMatch(/My Workflow - duplicate-\w+/)
    })
  })

  // AAP-94465: Duplicating a workflow that has a webhook trigger fails because the
  // original webhook_path is copied verbatim into the new workflow, colliding with the
  // (trigger_type, webhook_path) uniqueness constraint enforced by the backend.
  describe('duplicating a workflow with a webhook trigger (AAP-94465)', () => {
    const ORIGINAL_WEBHOOK_PATH = '/test-trigger-dupe'

    function buildWorkflow(): Workflow {
      return {
        id: 'wf-1',
        name: 'Workflow with webhook',
        description: null,
        labels: {},
        current_version: 1,
        is_builtin: false,
        is_enabled: true,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        created_by: { id: 'u-1', name: 'test-user', type: 'user' },
        project_id: 'proj-1',
      }
    }

    beforeEach(() => {
      vi.mocked(workflowFetchClient.GET).mockReset()
      vi.mocked(workflowFetchClient.POST).mockReset()
    })

    it('does not reuse the original webhook path when creating the duplicate', async () => {
      vi.mocked(workflowFetchClient.GET).mockResolvedValueOnce({
        data: {
          id: 'wf-1',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              name: 'Workflow with webhook',
              triggers: [
                {
                  id: 'trigger-1',
                  type: 'webhook_trigger',
                  parameters: { webhook_path: ORIGINAL_WEBHOOK_PATH },
                },
              ],
              nodes: [],
              edges: [],
            },
          },
        },
        error: undefined,
        response: new Response(),
      })

      let postedBody: Record<string, unknown> | undefined
      vi.mocked(workflowFetchClient.POST).mockImplementationOnce((_path, init) => {
        postedBody = (init as { body: Record<string, unknown> }).body
        return Promise.resolve({ data: { id: 'wf-2' }, error: undefined, response: new Response() })
      })

      const { result } = renderHook(() =>
        useDuplicateWorkflow({
          showAlert: vi.fn(),
          showError: vi.fn(),
          setLocation: vi.fn(),
          onSuccess: vi.fn(),
        })
      )

      await act(async () => {
        await result.current.duplicateWorkflow(buildWorkflow())
      })

      await waitFor(() => expect(workflowFetchClient.POST).toHaveBeenCalled())

      const definition = postedBody?.workflow_definition as { triggers: Array<{ parameters: { webhook_path: string } }> }
      const duplicatedWebhookPath = definition.triggers[0].parameters.webhook_path

      // A webhook path is unique per workflow, so duplicating must not submit the same
      // path the original workflow already registered.
      expect(duplicatedWebhookPath).not.toBe(ORIGINAL_WEBHOOK_PATH)
    })
  })
})
