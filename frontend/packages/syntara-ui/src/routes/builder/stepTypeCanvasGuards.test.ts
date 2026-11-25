import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import {
  importRefusal,
  stepTypeRefusal,
  useStepTypeCanvasGuards,
  verdictsFailClosedMessage,
} from './stepTypeCanvasGuards'
import {
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
  stepTypeBlockedMessage,
  stepTypeBlockedTooltip,
} from './stepTypePaletteGating'
import type { PendingImportData } from './useWorkflowImportExport'

const { mockShowError, mockNodeKinds } = vi.hoisted(() => ({
  mockShowError: vi.fn(),
  mockNodeKinds: {
    byKind: new Map<string, unknown>(),
    isLoading: false,
    isUnavailable: false,
  },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showError: mockShowError }),
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
} as unknown as Pick<WorkflowDefinition, 'workflow'>

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
    expect(verdictsFailClosedMessage(undefined, false)).toBe(STEP_TYPE_NO_PROJECT_TOOLTIP)
  })

  it('fails closed while the verdicts are pending or unavailable', () => {
    expect(verdictsFailClosedMessage('proj-1', true)).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })

  it('trusts the verdicts once they arrived', () => {
    expect(verdictsFailClosedMessage('proj-1', false)).toBeNull()
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
    expect(importRefusal(pendingImport(['http_request', 'script']), verdicts)).toBe(blockedMessage)
  })

  it('refuses a definition containing a blocked trigger', () => {
    const triggerDeny = { kind: 'manual_trigger', label: 'Manual trigger' } as const
    const blockedTrigger = {
      nodeKindByKind: registry(kind({ kind: 'manual_trigger', can_write: false, blocked_by: triggerDeny })),
      failClosedMessage: null,
    }
    expect(importRefusal(pendingImport([], ['manual_trigger']), blockedTrigger)).toBe(
      stepTypeBlockedMessage(triggerDeny)
    )
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
    const duplicateActivity = vi.fn()
    const onDuplicateRefused = vi.fn()
    const { result } = renderHook(() =>
      useStepTypeCanvasGuards({ projectId, currentWorkflow, duplicateActivity, onDuplicateRefused })
    )
    return { result, duplicateActivity, onDuplicateRefused }
  }

  it('refuses duplicating a blocked step type with the palette message', () => {
    const { result, duplicateActivity, onDuplicateRefused } = renderGuards()

    act(() => result.current.duplicateActivity('act-script'))

    expect(duplicateActivity).not.toHaveBeenCalled()
    expect(onDuplicateRefused).toHaveBeenCalledOnce()
    expect(mockShowError).toHaveBeenCalledWith({ title: 'Cannot duplicate step', description: blockedMessage })
  })

  it('duplicates a permitted step type', () => {
    const { result, duplicateActivity, onDuplicateRefused } = renderGuards()

    act(() => result.current.duplicateActivity('act-http'))

    expect(duplicateActivity).toHaveBeenCalledWith('act-http')
    expect(onDuplicateRefused).not.toHaveBeenCalled()
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it.each([
    ['loading', { isLoading: true, isUnavailable: false }],
    ['unavailable', { isLoading: false, isUnavailable: true }],
  ])('fails closed while the verdicts are %s', (_label, state) => {
    mockNodeKinds.isLoading = state.isLoading
    mockNodeKinds.isUnavailable = state.isUnavailable
    mockNodeKinds.byKind = new Map()
    const { result, duplicateActivity } = renderGuards()

    act(() => result.current.duplicateActivity('act-http'))

    expect(duplicateActivity).not.toHaveBeenCalled()
    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Cannot duplicate step',
      description: STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
    })
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBe(
      STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
    )
  })

  it('fails closed without a project (new workflow with no project picked)', () => {
    mockNodeKinds.byKind = new Map()
    const { result, duplicateActivity } = renderGuards(null)

    act(() => result.current.duplicateActivity('act-http'))

    expect(duplicateActivity).not.toHaveBeenCalled()
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBe(STEP_TYPE_NO_PROJECT_TOOLTIP)
  })

  it('exposes the import refusal for the builder project', () => {
    const { result } = renderGuards()

    expect(result.current.getImportRefusal(pendingImport(['script']))).toBe(blockedMessage)
    expect(result.current.getImportRefusal(pendingImport(['http_request']))).toBeNull()
  })
})
