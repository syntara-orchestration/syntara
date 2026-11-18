import { createContext } from 'react'

import type { ValidationError } from './builderReducer'

/** Findings from Save or Verify, scoped to the node being edited. */
export const WorkflowValidationContext = createContext<{
  errors: ValidationError[]
  nodeId?: string
}>({ errors: [] })
