import { DatePicker, FormGroup } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { formatDateYMD, parseDateYMD } from '../../../utils/dateUtils'
import { FormFieldError } from '../../FormFieldError'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'
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
  const { control } = useFormContext<FormDefinition>()
  const examples = getFormFieldBuilderExamplePlaceholders(FormFieldTypeEnum.DATE)
  const dateFieldId = `${idPrefix}-default-date`

  return (
    <FormGroup label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL} fieldId={`${idPrefix}-default`} labelHelp={labelHelp}>
      <Controller
        control={control}
        name={`fields.${index}.default`}
        render={({ field: rhfField, fieldState }) => {
          const defaultValue = rhfField.value
          const dateValue =
            typeof defaultValue === 'object' && defaultValue !== null && !Array.isArray(defaultValue)
              ? defaultValue
              : undefined
          const date = dateValue && 'date' in dateValue ? dateValue.date : undefined

          return (
            <>
              <DatePicker
                value={typeof date === 'string' ? date : ''}
                onChange={(_event, value) => {
                  rhfField.onChange(value === '' ? null : { ...dateValue, date: value })
                  commit()
                }}
                dateFormat={formatDateYMD}
                dateParse={parseDateYMD}
                isDisabled={isDisabled}
                aria-label={FORM_FIELD_BUILDER_INITIAL_ANSWER_DATE_ARIA_LABEL}
                inputProps={{
                  id: dateFieldId,
                  placeholder: `e.g. ${examples.defaultValue}`,
                  validated: fieldState.error ? 'error' : 'default',
                  onBlur: rhfField.onBlur,
                }}
                appendTo={() => document.body}
              />
              <FormFieldError error={fieldState.error} />
            </>
          )
        }}
      />
    </FormGroup>
  )
}
