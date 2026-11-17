import type { FormDefinition } from '@syntara/contracts'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { BuilderAction, ValidationError } from '../builderReducer'

import { isFormDefinitionValidationFindingForNode } from './validation/formDefinitionValidationFindings'
import { countBlockingValidationErrors } from './validation/mapFrontendValidationErrorsToBanner'

export function isStoredFormDefinitionValid(formDefinition: FormDefinition | undefined): boolean {
  const prepared = prepareFormDefinitionForCommit(formDefinition ?? { fields: [] })
  return safeParseFormDefinition(prepared).success
}

type ClearNodeValidationErrorsOptions = Readonly<{
  dispatch: (action: BuilderAction) => void
  getValidationErrors: () => ReadonlyArray<ValidationError>
  nodeId: string
  formDefinition: FormDefinition | undefined
}>

/** Remove verify/save banner findings for a node after its form definition validates locally. */
export function clearNodeValidationErrorsIfFormDefinitionValid(options: ClearNodeValidationErrorsOptions): void {
  const { dispatch, getValidationErrors, nodeId, formDefinition } = options
  if (!isStoredFormDefinitionValid(formDefinition)) {
    return
  }

  const validationErrors = getValidationErrors()
  const hasFormDefinitionFindings = validationErrors.some((error) =>
    isFormDefinitionValidationFindingForNode(error, nodeId)
  )
  if (!hasFormDefinitionFindings) {
    return
  }

  const remaining = validationErrors.filter((error) => !isFormDefinitionValidationFindingForNode(error, nodeId))

  dispatch({ type: 'CLEAR_NODE_VALIDATION_ERRORS', payload: { nodeId } })
  useWorkflowStore.getState().setValidationErrorCount(countBlockingValidationErrors(remaining))
}
