import { FormGroup } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldTypeEnum, type FormDefinitionSchemaInput } from '../../../forms'
import { coerceDateValueShape, includedDateComponents } from '../../../forms/dateFieldUtils'
import { FormFieldError } from '../../FormFieldError'
import { FormDateValueInputs } from '../FormDateValueInputs'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import {
  FORM_FIELD_BUILDER_INITIAL_ANSWER_DATE_ARIA_LABEL,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL,
} from './formFieldBuilderInitialAnswerCopy'

type FormFieldBuilderDateDefaultPickerProps = {
  index: number
  idPrefix: string
  isDisabled?: boolean
  labelHelp?: ReactElement
}

export function FormFieldBuilderDateDefaultPicker({
  index,
  idPrefix,
  isDisabled,
  labelHelp,
}: Readonly<FormFieldBuilderDateDefaultPickerProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control } = useFormContext<FormDefinitionSchemaInput>()
  const field = useWatch({ control, name: `fields.${index}` })

  if (field?.type !== FormFieldTypeEnum.DATE) {
    return null
  }

  const included = includedDateComponents(field)

  return (
    <FormGroup label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL} fieldId={`${idPrefix}-default`} labelHelp={labelHelp}>
      <Controller
        control={control}
        name={`fields.${index}.default`}
        render={({ field: rhfField, fieldState }) => (
          <>
            <FormDateValueInputs
              key={included.join(',')}
              included={included}
              value={coerceDateValueShape(rhfField.value)}
              onChange={(next) => {
                rhfField.onChange(next)
                commit()
              }}
              onBlur={rhfField.onBlur}
              idPrefix={`${idPrefix}-default`}
              isDisabled={isDisabled}
              validated={fieldState.error ? 'error' : 'default'}
              dateAriaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_DATE_ARIA_LABEL}
              timeAriaLabel="Initial answer time"
              timezoneAriaLabel="Initial answer time zone"
            />
            <FormFieldError error={fieldState.error} />
          </>
        )}
      />
    </FormGroup>
  )
}
