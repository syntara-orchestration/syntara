import { createContext } from 'react'

import type { FeatureFlagConfig } from '../utils/feature-flags'

export const FeatureFlagsContext = createContext<FeatureFlagConfig | null>(null)
