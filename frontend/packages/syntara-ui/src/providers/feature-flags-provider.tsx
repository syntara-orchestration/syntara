import { useState, type ReactNode } from 'react'

import { FEATURE_FLAG_NAMES, isFeatureFlagEnabled, type FeatureFlagConfig } from '../utils/feature-flags'

import { FeatureFlagsContext } from './feature-flags-context'

/** Reads saved browser feature flags once and provides them to React components. */
export function FeatureFlagsProvider(props: Readonly<{ children: ReactNode }>) {
  const [flags] = useState(() => {
    const snapshot: FeatureFlagConfig = {}
    for (const flagName of FEATURE_FLAG_NAMES) {
      snapshot[flagName] = isFeatureFlagEnabled(flagName)
    }
    return snapshot
  })

  return <FeatureFlagsContext.Provider value={flags}>{props.children}</FeatureFlagsContext.Provider>
}
