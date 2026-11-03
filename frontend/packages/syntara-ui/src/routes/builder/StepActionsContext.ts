import { use } from 'react'

import { NodeActionsContext, type NodeActionsContextValue } from './NodeActionsContext'

export type StepActionsContextValue = NodeActionsContextValue

export const StepActionsContext = NodeActionsContext

export function useStepActions(): StepActionsContextValue | null {
  return use(StepActionsContext)
}
