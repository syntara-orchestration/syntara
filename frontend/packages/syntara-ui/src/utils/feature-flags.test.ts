import { afterEach, beforeEach, describe, expect, expectTypeOf, it } from 'vitest'

import { FEATURE_FLAG_STORAGE_PREFIX, isFeatureFlagEnabled, toFeatureFlagKey } from './feature-flags'
import type { FeatureFlag, FeatureFlagStorageKey } from './feature-flags'

const workflowBuilderQolStorageKey = toFeatureFlagKey('workflow_builder_qol')

function clearFeatureFlagStorage() {
  for (let index = globalThis.localStorage.length - 1; index >= 0; index -= 1) {
    const key = globalThis.localStorage.key(index)
    if (key?.startsWith(FEATURE_FLAG_STORAGE_PREFIX)) {
      globalThis.localStorage.removeItem(key)
    }
  }
}

type IsFeatureFlagEnabled = typeof isFeatureFlagEnabled

beforeEach(() => {
  clearFeatureFlagStorage()
})

afterEach(() => {
  clearFeatureFlagStorage()
})

describe('feature flag TypeScript API', () => {
  it('uses the Syntara feature flag storage namespace', () => {
    expect(FEATURE_FLAG_STORAGE_PREFIX).toBe('syn.flags.')
    expect(workflowBuilderQolStorageKey).toBe('syn.flags.workflow_builder_qol')
    expectTypeOf<ReturnType<typeof toFeatureFlagKey>>().toEqualTypeOf<FeatureFlagStorageKey>()
  })

  it('only accepts names from the registered flag union', () => {
    expectTypeOf<IsFeatureFlagEnabled>().parameter(0).toEqualTypeOf<FeatureFlag>()
    expectTypeOf<'unregistered_flag'>().not.toExtend<FeatureFlag>()
  })
})

describe('isFeatureFlagEnabled', () => {
  it('defaults a missing flag to off', () => {
    expect(isFeatureFlagEnabled('workflow_builder_qol')).toBe(false)
  })

  it('enables a registered flag only for the string value true', () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'true')

    expect(isFeatureFlagEnabled('workflow_builder_qol')).toBe(true)
  })

  it('keeps a flag off when its stored value is false', () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'false')

    expect(isFeatureFlagEnabled('workflow_builder_qol')).toBe(false)
  })

  it('keeps a flag off when its stored value is not true or false', () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'yes')

    expect(isFeatureFlagEnabled('workflow_builder_qol')).toBe(false)
  })

  it('treats an unknown stored flag name as an invalid configuration', () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'true')
    globalThis.localStorage.setItem(`${FEATURE_FLAG_STORAGE_PREFIX}unregistered_flag`, 'true')

    expect(isFeatureFlagEnabled('workflow_builder_qol')).toBe(false)
  })
})
