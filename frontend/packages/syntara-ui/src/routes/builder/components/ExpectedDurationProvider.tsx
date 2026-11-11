import type { ReactNode } from 'react'

import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'

import { ExpectedDurationContext } from './expectedDurationContext'

export function ExpectedDurationProvider({ children }: Readonly<{ children: ReactNode }>) {
  const { defaults } = useWorkflowEngineDefaults()
  return <ExpectedDurationContext value={defaults?.expectedDurationSeconds ?? null}>{children}</ExpectedDurationContext>
}
