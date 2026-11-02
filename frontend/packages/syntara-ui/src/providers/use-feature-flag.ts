import { use } from 'react'

import type { FeatureFlag, FeatureFlagConfig } from '../utils/feature-flags'

import { FeatureFlagsContext } from './feature-flags-context'

/** Returns the current feature flag configuration from the provider. */
export function useFeatureFlags(): FeatureFlagConfig {
  const featureFlags = use(FeatureFlagsContext)
  if (featureFlags === null) {
    throw new Error('useFeatureFlags must be used within FeatureFlagsProvider')
  }

  return featureFlags
}

/** Returns whether a registered feature flag is enabled in the current app snapshot. */
export function useFeatureFlag(flagName: FeatureFlag): boolean {
  const featureFlags = use(FeatureFlagsContext)
  if (featureFlags === null) {
    throw new Error('useFeatureFlag must be used within FeatureFlagsProvider')
  }

  return featureFlags[flagName] === true
}
