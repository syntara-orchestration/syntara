import { FormGroup } from '@patternfly/react-core'
import type { ReactElement } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldTypeEnum, type FormDefinitionSchemaInput } from '../../../forms'
import {
  coerceDateValueShape,
  DATE_COMPONENT_NAMES,
  includedDateComponents,
  type DateComponentName,
} from '../../../forms/dateFieldUtils'
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

function getDefaultComponentsError(value: unknown, included: DateComponentName[]): string | undefined {
  if (value == null) {
    return undefined
  }

  const defaultValue = coerceDateValueShape(value)
  if (defaultValue === null) {
    return undefined
  }

  const missing = included.filter((component) => defaultValue[component] == null)
  const extra = DATE_COMPONENT_NAMES.filter(
    (component) => !included.includes(component) && defaultValue[component] != null
  )
  const messages = [
    missing.length > 0 ? `Default is missing ${missing.join(', ')}` : undefined,
    extra.length > 0 ? `Default supplies ${extra.join(', ')}, which this field does not collect` : undefined,
  ].filter((message): message is string => message !== undefined)

  return messages.length > 0 ? messages.join('. ') : undefined
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
        render={({ field: rhfField, fieldState }) => {
          const value = coerceDateValueShape(rhfField.value)
          const componentsError = getDefaultComponentsError(rhfField.value, included)

          return (
            <>
              <FormDateValueInputs
                key={included.join(',')}
                included={included}
                value={value}
                onChange={(next) => {
                  rhfField.onChange(next)
                  commit()
                }}
                onBlur={rhfField.onBlur}
                idPrefix={`${idPrefix}-default`}
                isDisabled={isDisabled}
                validated={fieldState.error || componentsError ? 'error' : 'default'}
                dateAriaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_DATE_ARIA_LABEL}
                timeAriaLabel="Initial answer time"
                timezoneAriaLabel="Initial answer time zone"
              />
              <FormFieldError message={componentsError} error={fieldState.error} />
            </>
          )
        }}
      />
    </FormGroup>
  )
}
