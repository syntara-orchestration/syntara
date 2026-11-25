import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import {
  blockedStepTypesIn,
  importRefusal,
  stepTypeRefusal,
  useStepTypeCanvasGuards,
  verdictsFailClosedMessage,
  withoutStepTypes,
  type CanvasDefinition,
} from './stepTypeCanvasGuards'
import {
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_LOADING_MESSAGE,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
  stepTypeBlockedMessage,
  stepTypeBlockedTooltip,
} from './stepTypePaletteGating'
import type { PendingImportData } from './useWorkflowImportExport'

const { mockShowError, mockNodeKinds, mockCurrentWorkflow } = vi.hoisted(() => ({
  mockShowError: vi.fn(),
  mockCurrentWorkflow: vi.fn<() => unknown>(),
  mockNodeKinds: {
    byKind: new Map<string, unknown>(),
    isLoading: false,
    isUnavailable: false,
  },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: { getState: () => ({ currentWorkflow: mockCurrentWorkflow() }) },
}))

vi.mock('../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    nodeKindByKind: mockNodeKinds.byKind,
    isLoading: mockNodeKinds.isLoading,
    isUnavailable: mockNodeKinds.isUnavailable,
  }),
}))

const scriptDeny = { kind: 'script', label: 'Script' } as const
const blockedMessage = stepTypeBlockedMessage(scriptDeny)
const scriptImportRefusal = "You don't have permission to write Script steps."

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return { category: 'action', can_write: true, blocked_by: null, ...overrides }
}

function registry(...entries: NodeKind[]): Map<string, NodeKind> {
  return new Map(entries.map((entry) => [entry.kind, entry]))
}

const verdictsByKind = registry(
  kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
  kind({ kind: 'http_request' }),
  kind({ kind: 'manual_trigger', category: 'trigger' })
)

const currentWorkflow = {
  workflow: {
    activities: [
      { id: 'act-script', type: 'script', name: 'Script' },
      { id: 'act-http', type: 'http_request', name: 'HTTP' },
    ],
  },
}

function pendingImport(activityTypes: string[], triggerTypes: string[] = []): PendingImportData {
  return {
    workflowDef: {
      name: 'Imported',
      schema_version: '2.0.0',
      workflow: { activities: activityTypes.map((type, i) => ({ id: `a${i}`, type, name: type })) },
      triggers: triggerTypes.map((type, i) => ({ id: `t${i}`, type, name: type })),
    } as unknown as PendingImportData['workflowDef'],
    edges: [],
    nodePositions: {},
    name: 'Imported',
    description: '',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCurrentWorkflow.mockReturnValue(currentWorkflow)
  mockNodeKinds.byKind = verdictsByKind
  mockNodeKinds.isLoading = false
  mockNodeKinds.isUnavailable = false
})

describe('stepTypeBlockedMessage', () => {
  it('uses the add-step panel tooltip wording', () => {
    expect(blockedMessage).toBe(stepTypeBlockedTooltip(scriptDeny))
  })
})

describe('verdictsFailClosedMessage', () => {
  it('fails closed without a project', () => {
    expect(verdictsFailClosedMessage(undefined, false, false)).toBe(STEP_TYPE_NO_PROJECT_TOOLTIP)
  })

  it('says the verdicts are still loading', () => {
    expect(verdictsFailClosedMessage('proj-1', true, false)).toBe(STEP_TYPE_PERMISSIONS_LOADING_MESSAGE)
  })

  it('says the verdicts are unavailable', () => {
    expect(verdictsFailClosedMessage('proj-1', false, true)).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })

  it('trusts the verdicts once they arrived', () => {
    expect(verdictsFailClosedMessage('proj-1', false, false)).toBeNull()
  })
})

describe('stepTypeRefusal', () => {
  const verdicts = { nodeKindByKind: verdictsByKind, failClosedMessage: null }

  it('refuses a blocked kind with the palette message', () => {
    expect(stepTypeRefusal('script', verdicts)).toBe(blockedMessage)
  })

  it('allows a permitted kind and a kind with no verdict', () => {
    expect(stepTypeRefusal('http_request', verdicts)).toBeNull()
    expect(stepTypeRefusal('unknown_kind', verdicts)).toBeNull()
  })

  it('refuses a blocked kind without a reason as unavailable', () => {
    const noReason = { nodeKindByKind: registry(kind({ kind: 'script', can_write: false })), failClosedMessage: null }
    expect(stepTypeRefusal('script', noReason)).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })

  it('refuses every kind while failing closed', () => {
    const failClosed = { nodeKindByKind: verdictsByKind, failClosedMessage: STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP }
    expect(stepTypeRefusal('http_request', failClosed)).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })
})

describe('importRefusal', () => {
  const verdicts = { nodeKindByKind: verdictsByKind, failClosedMessage: null }

  it('refuses a definition containing a blocked activity', () => {
    expect(importRefusal(pendingImport(['http_request', 'script']), verdicts)).toBe(scriptImportRefusal)
  })

  it('refuses a definition containing a blocked trigger', () => {
    const triggerDeny = { kind: 'manual_trigger', label: 'Manual trigger' } as const
    const blockedTrigger = {
      nodeKindByKind: registry(kind({ kind: 'manual_trigger', can_write: false, blocked_by: triggerDeny })),
      failClosedMessage: null,
    }
    expect(importRefusal(pendingImport([], ['manual_trigger']), blockedTrigger)).toBe(
      "You don't have permission to write Manual trigger steps."
    )
  })

  it('names every blocked step type once, in the order they first appear', () => {
    const approvalDeny = { kind: 'approval', label: 'Approval' } as const
    const emailDeny = { kind: 'email', label: 'Email' } as const
    const manyBlocked = {
      nodeKindByKind: registry(
        kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
        kind({ kind: 'approval', can_write: false, blocked_by: approvalDeny }),
        kind({ kind: 'email', category: 'trigger', can_write: false, blocked_by: emailDeny }),
        kind({ kind: 'http_request' })
      ),
      failClosedMessage: null,
    }

    expect(importRefusal(pendingImport(['script', 'http_request', 'approval', 'script']), manyBlocked)).toBe(
      "You don't have permission to write Script and Approval steps."
    )
    expect(importRefusal(pendingImport(['approval', 'script', 'approval'], ['email']), manyBlocked)).toBe(
      "You don't have permission to write Approval, Script and Email steps."
    )
  })

  it('keeps refusing a blocked kind with no reported reason', () => {
    const unexplained = {
      nodeKindByKind: registry(
        kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
        kind({ kind: 'approval', can_write: false, blocked_by: null })
      ),
      failClosedMessage: null,
    }
    expect(importRefusal(pendingImport(['script', 'approval']), unexplained)).toBe(
      STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
    )
  })

  it('allows kinds with no verdict', () => {
    expect(importRefusal(pendingImport(['unknown_kind']), verdicts)).toBeNull()
  })

  it('returns the fail-closed message even when blocked kinds are present', () => {
    const failClosed = { nodeKindByKind: verdictsByKind, failClosedMessage: STEP_TYPE_PERMISSIONS_LOADING_MESSAGE }
    expect(importRefusal(pendingImport(['script']), failClosed)).toBe(STEP_TYPE_PERMISSIONS_LOADING_MESSAGE)
  })

  it('allows a definition with only permitted kinds', () => {
    expect(importRefusal(pendingImport(['http_request'], ['manual_trigger']), verdicts)).toBeNull()
  })

  it('refuses even an empty definition while failing closed', () => {
    const failClosed = { nodeKindByKind: verdictsByKind, failClosedMessage: STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP }
    expect(importRefusal(pendingImport([]), failClosed)).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })
})

describe('useStepTypeCanvasGuards', () => {
  function renderGuards(projectId: string | null = 'proj-1') {
    return renderHook(() => useStepTypeCanvasGuards({ projectId }))
  }

  it('refuses duplicating a blocked step type with the palette message', () => {
    const { result } = renderGuards()

    expect(result.current.canDuplicateActivity('act-script')).toBe(false)
    expect(mockShowError).toHaveBeenCalledWith({ title: 'Cannot duplicate step', description: blockedMessage })
  })

  it('allows duplicating a permitted step type', () => {
    const { result } = renderGuards()

    expect(result.current.canDuplicateActivity('act-http')).toBe(true)
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('keeps the same duplicate check when the workflow changes', () => {
    const { result, rerender } = renderGuards()
    const before = result.current.canDuplicateActivity

    mockCurrentWorkflow.mockReturnValue({ workflow: { activities: [{ id: 'act-new', type: 'script', name: 'New' }] } })
    rerender()

    expect(result.current.canDuplicateActivity).toBe(before)
    expect(result.current.canDuplicateActivity('act-new')).toBe(false)
  })

  it.each([
    ['loading', { isLoading: true, isUnavailable: false }, STEP_TYPE_PERMISSIONS_LOADING_MESSAGE],
    ['unavailable', { isLoading: false, isUnavailable: true }, STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP],
  ])('fails closed while the verdicts are %s', (_label, state, message) => {
    mockNodeKinds.isLoading = state.isLoading
    mockNodeKinds.isUnavailable = state.isUnavailable
    mockNodeKinds.byKind = new Map()
    const { result } = renderGuards()

    expect(result.current.canDuplicateActivity('act-http')).toBe(false)
    expect(mockShowError).toHaveBeenCalledWith({ title: 'Cannot duplicate step', description: message })
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBe(message)
  })

  it('fails closed without a project (new workflow with no project picked)', () => {
    mockNodeKinds.byKind = new Map()
    const { result } = renderGuards(null)

    expect(result.current.canDuplicateActivity('act-http')).toBe(false)
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBe(STEP_TYPE_NO_PROJECT_TOOLTIP)
  })

  it('exposes the import refusal for the builder project', () => {
    const { result } = renderGuards()

    expect(result.current.getImportRefusal(pendingImport(['script']))).toBe(scriptImportRefusal)
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBeNull()
  })
})

describe('blockedStepTypesIn', () => {
  function definition(activityTypes: string[], triggerTypes: string[] = []) {
    return pendingImport(activityTypes, triggerTypes).workflowDef
  }

  it('lists a blocked activity type by its step type label', () => {
    expect(blockedStepTypesIn(definition(['http_request', 'script']), verdictsByKind)).toEqual([scriptDeny])
  })

  it('lists a blocked trigger type', () => {
    const triggerDeny = { kind: 'manual_trigger', label: 'Manual trigger' } as const
    const byKind = registry(
      kind({ kind: 'manual_trigger', category: 'trigger', can_write: false, blocked_by: triggerDeny })
    )
    expect(blockedStepTypesIn(definition([], ['manual_trigger']), byKind)).toEqual([triggerDeny])
  })

  it('allows permitted kinds and kinds with no verdict', () => {
    expect(
      blockedStepTypesIn(definition(['http_request', 'unknown_kind'], ['manual_trigger']), verdictsByKind)
    ).toEqual([])
  })

  it('lists each blocked kind once, in first-seen order, falling back to the kind', () => {
    const byKind = registry(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request', can_write: false })
    )
    expect(blockedStepTypesIn(definition(['http_request', 'script', 'http_request', 'script']), byKind)).toEqual([
      { kind: 'http_request', label: 'http_request' },
      scriptDeny,
    ])
  })
})

describe('withoutStepTypes', () => {
  function canvasDefinition(): CanvasDefinition {
    return {
      workflowDef: {
        name: 'Run',
        workflow: {
          activities: [
            { id: 'a-http', type: 'http_request', name: 'HTTP' },
            { id: 'a-script', type: 'script', name: 'Script' },
            { id: 'a-untyped', name: 'Untyped' },
          ],
        },
        triggers: [
          { id: 't-manual', type: 'manual_trigger', name: 'Manual' },
          { id: 't-webhook', type: 'webhook_trigger', name: 'Webhook' },
        ],
      } as unknown as CanvasDefinition['workflowDef'],
      edges: [
        { id: 'e1', source: 't-manual', target: 'a-http' },
        { id: 'e2', source: 'a-http', target: 'a-script' },
        { id: 'e3', source: 't-webhook', target: 'a-untyped' },
      ],
      nodePositions: {
        'a-http': { x: 0, y: 0 },
        'a-script': { x: 1, y: 1 },
        't-manual': { x: 2, y: 2 },
        't-webhook': { x: 3, y: 3 },
      },
    }
  }

  it('drops the steps of the given types with their edges and positions', () => {
    const result = withoutStepTypes(canvasDefinition(), ['script', 'manual_trigger'])

    expect(result.workflowDef.workflow.activities.map((a) => a.id)).toEqual(['a-http', 'a-untyped'])
    expect(result.workflowDef.triggers?.map((t) => t.id)).toEqual(['t-webhook'])
    expect(result.edges.map((e) => e.id)).toEqual(['e3'])
    expect(Object.keys(result.nodePositions)).toEqual(['a-http', 't-webhook'])
    expect(result.workflowDef.name).toBe('Run')
  })

  it('does not mutate the input', () => {
    const input = canvasDefinition()
    const snapshot = structuredClone(input)

    withoutStepTypes(input, ['script', 'manual_trigger'])

    expect(input).toEqual(snapshot)
  })
})
