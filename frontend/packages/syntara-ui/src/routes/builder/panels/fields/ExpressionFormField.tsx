import { FormGroup } from '@patternfly/react-core'
import { useState } from 'react'

import { EXPRESSION_FIELD_PLACEHOLDER } from '../../../../components/expressions/expressionFieldDrag'
import { ExpressionFieldInput } from '../../../../components/forms/ExpressionFieldInput'

type ExpressionFormFieldProps = {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  isRequired?: boolean
  error?: string
}

/** Builder expression field using shared {@link ExpressionFieldInput} for drag/drop and syntax validation. */
function ExpressionFormField({
  id,
  label,
  value,
  onChange,
  placeholder = EXPRESSION_FIELD_PLACEHOLDER,
  isRequired = false,
  error,
}: Readonly<ExpressionFormFieldProps>) {
  const [isDropTarget, setIsDropTarget] = useState(false)

  return (
    <FormGroup
      label={label}
      isRequired={isRequired}
      fieldId={id}
      data-drop-target={isDropTarget ? 'active' : 'inactive'}
    >
      {/* Uses FormFieldError (with icon) via ExpressionFieldInput for SynForm field parity. */}
      <ExpressionFieldInput
        id={id}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        externalError={error}
        onDropTargetChange={setIsDropTarget}
      />
    </FormGroup>
  )
}

export { ExpressionFormField }
export type { ExpressionFormFieldProps }
