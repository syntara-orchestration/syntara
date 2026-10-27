import { ActivityTypeEnum, RegistryStepId } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { resolveNodeKind } from './nodeKindMapping'

describe('resolveNodeKind', () => {
  it.each([
    [RegistryStepId.ACTION_API, ActivityTypeEnum.HTTP_REQUEST],
    [RegistryStepId.AGENT, ActivityTypeEnum.AGENTIC],
    [RegistryStepId.AAP_WORKFLOW_TEMPLATE, ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE],
  ])('translates %s to the backend kind', (id, kind) => {
    expect(resolveNodeKind(id)).toBe(kind)
  })

  it.each([
    RegistryStepId.TRIGGER,
    RegistryStepId.ACTION,
    RegistryStepId.LOGIC,
    RegistryStepId.AAP_EXECUTION,
    RegistryStepId.GENERIC,
    'action-internal-activity',
    'unknown-step',
    'toString',
    '__proto__',
  ])('returns null for unmapped id %s without guessing a kind', (id) => {
    expect(resolveNodeKind(id)).toBeNull()
  })
})
