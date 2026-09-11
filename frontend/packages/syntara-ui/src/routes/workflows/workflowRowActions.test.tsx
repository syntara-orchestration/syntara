import type { WorkflowAPI } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { builtinProjectTooltip } from '../../hooks/permissionUtils'

import type { useWorkflowPermissions } from './useWorkflowPermissions'
import { buildWorkflowRowActions } from './workflowRowActions'

vi.mock('@tanstack/react-router', () => ({ useNavigate: vi.fn() }))
vi.mock('../../components/IconLabel', () => ({
  IconLabel: ({ children }: { children: React.ReactNode }) => children,
}))

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']
type Permissions = ReturnType<typeof useWorkflowPermissions>

const basePermissions: Permissions = {
  canCreate: true,
  canUpdate: true,
  canDelete: true,
  canRun: true,
  isLoading: false,
  tooltips: {
    create: 'No create permission',
    duplicate: 'No duplicate permission',
    update: 'No update permission',
    delete: 'No delete permission',
    run: 'No run permission',
  },
}

const baseCallbacks = {
  navigate: vi.fn() as never,
  onRun: vi.fn(),
  onDuplicate: vi.fn(),
  onExport: vi.fn(),
  onPublish: vi.fn(),
  onUnpublish: vi.fn(),
  onDelete: vi.fn(),
  isDuplicating: false,
}

const baseWorkflow: Workflow = {
  id: 'wf-1',
  name: 'My Workflow',
  is_builtin: false,
  published_version_id: null,
  project_id: 'proj-1',
} as Workflow

describe('buildWorkflowRowActions', () => {
  describe('builtin workflow', () => {
    it('returns empty array when workflow.is_builtin is true regardless of isBuiltinProject', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, is_builtin: true },
        basePermissions,
        false,
        baseCallbacks
      )
      expect(actions).toEqual([])
    })

    it('returns empty array even when isBuiltinProject is also true', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, is_builtin: true },
        basePermissions,
        true,
        baseCallbacks
      )
      expect(actions).toEqual([])
    })
  })

  describe('isBuiltinProject: true', () => {
    it('disables edit with builtin tooltip', () => {
      const actions = buildWorkflowRowActions(baseWorkflow, basePermissions, true, baseCallbacks)
      const edit = actions.find((a) => a.key === 'edit')
      expect(edit?.isAriaDisabled).toBe(true)
      expect(edit?.tooltipProps?.content).toBe(builtinProjectTooltip('edit this workflow'))
    })

    it('disables duplicate with builtin tooltip', () => {
      const actions = buildWorkflowRowActions(baseWorkflow, basePermissions, true, baseCallbacks)
      const dup = actions.find((a) => a.key === 'duplicate')
      expect(dup?.isAriaDisabled).toBe(true)
      expect(dup?.tooltipProps?.content).toBe(builtinProjectTooltip('duplicate this workflow'))
    })

    it('disables publish with builtin tooltip', () => {
      const actions = buildWorkflowRowActions(baseWorkflow, basePermissions, true, baseCallbacks)
      const publish = actions.find((a) => a.key === 'publish')
      expect(publish?.isAriaDisabled).toBe(true)
      expect(publish?.tooltipProps?.content).toBe(builtinProjectTooltip('publish this workflow'))
    })

    it('disables delete with builtin tooltip', () => {
      const actions = buildWorkflowRowActions(baseWorkflow, basePermissions, true, baseCallbacks)
      const del = actions.find((a) => a.key === 'delete')
      expect(del?.isAriaDisabled).toBe(true)
      expect(del?.tooltipProps?.content).toBe(builtinProjectTooltip('delete this workflow'))
    })

    it('includes unpublish disabled with builtin tooltip when workflow is published', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, published_version_id: 'v1' },
        basePermissions,
        true,
        baseCallbacks
      )
      const unpublish = actions.find((a) => a.key === 'unpublish')
      expect(unpublish?.isAriaDisabled).toBe(true)
      expect(unpublish?.tooltipProps?.content).toBe(builtinProjectTooltip('unpublish this workflow'))
    })

    it('does not disable run based on isBuiltinProject', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, published_version_id: 'v1' },
        basePermissions,
        true,
        baseCallbacks
      )
      const run = actions.find((a) => a.key === 'run')
      expect(run?.isAriaDisabled).toBe(false)
    })
  })

  describe('isBuiltinProject: false — falls through to permission tooltips', () => {
    it('disables edit with permission tooltip when canUpdate is false', () => {
      const actions = buildWorkflowRowActions(
        baseWorkflow,
        { ...basePermissions, canUpdate: false },
        false,
        baseCallbacks
      )
      const edit = actions.find((a) => a.key === 'edit')
      expect(edit?.isAriaDisabled).toBe(true)
      expect(edit?.tooltipProps?.content).toBe('No update permission')
    })

    it('disables duplicate with permission tooltip when canCreate is false', () => {
      const actions = buildWorkflowRowActions(
        baseWorkflow,
        { ...basePermissions, canCreate: false },
        false,
        baseCallbacks
      )
      const dup = actions.find((a) => a.key === 'duplicate')
      expect(dup?.isAriaDisabled).toBe(true)
      expect(dup?.tooltipProps?.content).toBe('No duplicate permission')
    })

    it('disables delete with permission tooltip when canDelete is false', () => {
      const actions = buildWorkflowRowActions(
        baseWorkflow,
        { ...basePermissions, canDelete: false },
        false,
        baseCallbacks
      )
      const del = actions.find((a) => a.key === 'delete')
      expect(del?.isAriaDisabled).toBe(true)
      expect(del?.tooltipProps?.content).toBe('No delete permission')
    })

    it('all actions are enabled when user has full permissions and workflow is published', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, published_version_id: 'v1' },
        basePermissions,
        false,
        baseCallbacks
      )
      const gated = actions.filter((a) => !a.isSeparator && a.isAriaDisabled)
      expect(gated).toHaveLength(0)
    })
  })

  describe('unpublish action', () => {
    it('is absent when workflow has no published version', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, published_version_id: null },
        basePermissions,
        false,
        baseCallbacks
      )
      expect(actions.find((a) => a.key === 'unpublish')).toBeUndefined()
    })

    it('is present when workflow has a published version', () => {
      const actions = buildWorkflowRowActions(
        { ...baseWorkflow, published_version_id: 'v1' },
        basePermissions,
        false,
        baseCallbacks
      )
      expect(actions.find((a) => a.key === 'unpublish')).toBeDefined()
    })
  })
})
