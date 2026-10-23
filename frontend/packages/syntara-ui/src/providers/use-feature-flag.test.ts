import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { toFeatureFlagKey } from '../utils/feature-flags'

import { FeatureFlagsProvider } from './feature-flags-provider'
import { useFeatureFlag } from './use-feature-flag'

const workflowBuilderQolStorageKey = toFeatureFlagKey('workflow_builder_qol')

describe('useFeatureFlag', () => {
  beforeEach(() => {
    globalThis.localStorage.removeItem(workflowBuilderQolStorageKey)
  })

  afterEach(() => {
    globalThis.localStorage.removeItem(workflowBuilderQolStorageKey)
  })

  it('throws when used outside FeatureFlagsProvider', () => {
    expect(() => renderHook(() => useFeatureFlag('workflow_builder_qol'))).toThrow(
      'useFeatureFlag must be used within FeatureFlagsProvider'
    )
  })

  it('returns true when the registered flag is enabled in local storage', () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'true')

    const { result } = renderHook(() => useFeatureFlag('workflow_builder_qol'), {
      wrapper: FeatureFlagsProvider,
    })

    expect(result.current).toBe(true)
  })

  it('returns false when the flag is missing from local storage', () => {
    const { result } = renderHook(() => useFeatureFlag('workflow_builder_qol'), {
      wrapper: FeatureFlagsProvider,
    })

    expect(result.current).toBe(false)
  })
})
