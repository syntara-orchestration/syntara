import { Checkbox, FormGroup, TextInput } from '@patternfly/react-core'
import type { FormDefinition, FormField } from '@syntara/contracts'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { FormFieldHintOrError } from '../../FormFieldError'
import { SynTextField } from '../SynTextField'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { FormFieldBuilderDateDefaultPicker } from './FormFieldBuilderDateDefaultPicker'
import { FormFieldBuilderDropdownDefaultSelect } from './FormFieldBuilderDropdownDefaultSelect'
import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'
import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'
import { FormFieldBuilderMultiSelectDefaultCheckboxes } from './FormFieldBuilderMultiSelectDefaultCheckboxes'

type FormFieldBuilderFieldDefaultEditorProps = {
  index: number
  field: FormField
  isDisabled?: boolean
  idPrefix: string
}

export function FormFieldBuilderFieldDefaultEditor({
  index,
  field,
  isDisabled,
  idPrefix,
}: Readonly<FormFieldBuilderFieldDefaultEditorProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control } = useFormContext<FormDefinition>()

  const defaultValueLabelHelp = formFieldBuilderLabelHelp('defaultValue', 'Default value')
  const examples = getFormFieldBuilderExamplePlaceholders(field.type)

  if (field.type === FormFieldTypeEnum.CHECKBOX) {
    return (
      <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={defaultValueLabelHelp}>
        <Controller
          control={control}
          name={`fields.${index}.default`}
          render={({ field: rhfField }) => (
            <Checkbox
              id={`${idPrefix}-default`}
              label="Default to checked"
              isChecked={Boolean(rhfField.value)}
              isDisabled={isDisabled}
              onChange={(_event, checked) => {
                rhfField.onChange(checked)
                commit()
              }}
            />
          )}
        />
      </FormGroup>
    )
  }

  if (field.type === FormFieldTypeEnum.NUMBER) {
    return (
      <Controller
        control={control}
        name={`fields.${index}.default`}
        render={({ field: rhfField }) => (
          <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={defaultValueLabelHelp}>
            <TextInput
              id={`${idPrefix}-default`}
              type="number"
              aria-label="Default value"
              placeholder={examples.defaultValue}
              isDisabled={isDisabled}
              value={rhfField.value === null || rhfField.value === undefined ? '' : String(rhfField.value)}
              onChange={(_event, value) => {
                if (value === '') {
                  rhfField.onChange(null)
                  return
                }
                const parsed = Number.parseFloat(value)
                rhfField.onChange(Number.isFinite(parsed) ? parsed : null)
                commit()
              }}
              onBlur={rhfField.onBlur}
            />
          </FormGroup>
        )}
      />
    )
  }

  if (field.type === FormFieldTypeEnum.DROPDOWN || field.type === FormFieldTypeEnum.MULTI_SELECT) {
    if (field.options.source === 'dynamic') {
      return (
        <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={defaultValueLabelHelp}>
          <FormFieldHintOrError hint="Default values are not available when options are populated dynamically at runtime." />
        </FormGroup>
      )
    }
    if (field.type === FormFieldTypeEnum.DROPDOWN) {
      return (
        <FormFieldBuilderDropdownDefaultSelect
          index={index}
          idPrefix={idPrefix}
          isDisabled={isDisabled}
          labelHelp={defaultValueLabelHelp}
        />
      )
    }
    return (
      <FormFieldBuilderMultiSelectDefaultCheckboxes
        index={index}
        idPrefix={idPrefix}
        isDisabled={isDisabled}
        labelHelp={defaultValueLabelHelp}
      />
    )
  }

  if (field.type === FormFieldTypeEnum.DATE) {
    return (
      <FormFieldBuilderDateDefaultPicker
        index={index}
        idPrefix={idPrefix}
        isDisabled={isDisabled}
        labelHelp={defaultValueLabelHelp}
      />
    )
  }

  if (
    field.type === FormFieldTypeEnum.TEXT ||
    field.type === FormFieldTypeEnum.TEXTAREA ||
    field.type === FormFieldTypeEnum.MASKED_TEXT ||
    field.type === FormFieldTypeEnum.EMAIL
  ) {
    return (
      <SynTextField
        name={`fields.${index}.default`}
        control={control}
        label="Default value"
        fieldId={`${idPrefix}-default`}
        isDisabled={isDisabled}
        labelHelp={defaultValueLabelHelp}
        placeholder={examples.defaultValue}
        onValueChange={commit}
      />
    )
  }

  return null
}
