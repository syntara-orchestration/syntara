import { Content, FormGroup, FormHelperText, HelperText, HelperTextItem } from '@patternfly/react-core'

import { EXECUTION_PLANE_SCOPE_HELP } from '../integrationFieldHelpText'

type ExecutionPlaneScopeFieldProps = Readonly<{
  /** DOM id for the scope value element; also used as FormGroup fieldId. */
  fieldId: string
}>

/** Read-only Global scope display for Execution plane (OpenShift) integrations. */
export function ExecutionPlaneScopeField({ fieldId }: ExecutionPlaneScopeFieldProps) {
  return (
    <FormGroup label="Scope" fieldId={fieldId}>
      <Content id={fieldId}>Global</Content>
      <FormHelperText>
        <HelperText>
          <HelperTextItem>{EXECUTION_PLANE_SCOPE_HELP}</HelperTextItem>
        </HelperText>
      </FormHelperText>
    </FormGroup>
  )
}
