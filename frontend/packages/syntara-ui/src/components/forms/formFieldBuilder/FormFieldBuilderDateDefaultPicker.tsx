import { DatePicker, FormGroup } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { formatDateYMD, parseDateYMD } from '../../../utils/dateUtils'
import { FormFieldError } from '../../FormFieldError'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'

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
    <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={labelHelp}>
      <Controller
        control={control}
        name={`fields.${index}.default`}
        render={({ field: rhfField, fieldState }) => (
          <>
            <DatePicker
              value={typeof rhfField.value === 'string' ? rhfField.value : ''}
              onChange={(_event, value) => {
                rhfField.onChange(value === '' ? null : value)
                commit()
              }}
              dateFormat={formatDateYMD}
              dateParse={parseDateYMD}
              isDisabled={isDisabled}
              aria-label="Default date"
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
        )}
      />
    </FormGroup>
  )
}
