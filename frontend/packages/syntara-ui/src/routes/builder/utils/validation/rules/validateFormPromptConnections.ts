import type { Activity } from '@syntara/contracts'
import { EdgeHandleEnum } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import type { ValidationError } from '../types'

import { validateBranchConnections } from './validateBranchConnections'

/**
 * Validates that form prompt nodes have a connection from the 'submitted' branch.
 */
export function validateFormPromptConnections(activities: Activity[], edges: EdgeConnection[]): ValidationError[] {
  return validateBranchConnections(activities, edges, {
    nodeFilter: (a) => a.type === 'form_prompt',
    requiredHandle: EdgeHandleEnum.SUBMITTED,
    nodeTypeName: 'Form',
    branchName: 'Submitted',
    errorIdPrefix: 'form-prompt-missing-submitted',
    ruleName: 'form-prompt-connections',
  })
}
