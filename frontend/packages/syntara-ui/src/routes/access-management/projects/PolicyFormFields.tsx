import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'

import { PROJECT_POLICY_NAME_HINT, STATEMENTS_JSON_HINT } from './addProjectPolicySchema'
import { NodeKindStatementBuilder } from './NodeKindStatementBuilder'

type PolicyFormFieldsProps = {
  statementsJson: string
  onAppendStatement: (statementsJson: string) => void
}

export function PolicyFormFields({ statementsJson, onAppendStatement }: Readonly<PolicyFormFieldsProps>) {
  return (
    <>
      <SynTextField
        name="name"
        label="Policy name"
        fieldId="project-policy-name"
        isRequired
        hint={PROJECT_POLICY_NAME_HINT}
      />
      <SynTextField name="description" label="Policy description" fieldId="project-policy-description" />
      <NodeKindStatementBuilder statementsJson={statementsJson} onAppend={onAppendStatement} />
      <SynTextAreaField
        name="statementsJson"
        label="Policy statements JSON"
        fieldId="project-policy-statements"
        isRequired
        hint={STATEMENTS_JSON_HINT}
        rows={10}
        resizeOrientation="vertical"
      />
    </>
  )
}
