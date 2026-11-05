import { Checkbox, FormGroup } from '@patternfly/react-core'
import type { FormDefinition, FormField } from '@syntara/contracts'
import { Controller, useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { FormFieldError, FormFieldHintOrError } from '../../FormFieldError'
import { SynNumberInputControl } from '../SynNumberInputControl'
import { SynTextField } from '../SynTextField'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { FormFieldBuilderDateDefaultPicker } from './FormFieldBuilderDateDefaultPicker'
import { FormFieldBuilderDropdownDefaultSelect } from './FormFieldBuilderDropdownDefaultSelect'
import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'
import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'
import {
  FORM_FIELD_BUILDER_INITIAL_ANSWER_CHECKBOX_LABEL,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_DYNAMIC_UNAVAILABLE_HINT,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL,
} from './formFieldBuilderInitialAnswerCopy'
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

  const defaultValueLabelHelp = formFieldBuilderLabelHelp('defaultValue', FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL)
  const examples = getFormFieldBuilderExamplePlaceholders(field.type)

  if (field.type === FormFieldTypeEnum.CHECKBOX) {
    return (
      <FormGroup
        label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
        fieldId={`${idPrefix}-default`}
        labelHelp={defaultValueLabelHelp}
      >
        <Controller
          control={control}
          name={`fields.${index}.default`}
          render={({ field: rhfField, fieldState }) => (
            <>
              <Checkbox
                id={`${idPrefix}-default`}
                label={FORM_FIELD_BUILDER_INITIAL_ANSWER_CHECKBOX_LABEL}
                isChecked={Boolean(rhfField.value)}
                isDisabled={isDisabled}
                onChange={(_event, checked) => {
                  rhfField.onChange(checked)
                  commit()
                }}
              />
              <FormFieldError error={fieldState.error} />
            </>
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
        render={({ field: rhfField, fieldState }) => (
          <FormGroup
            label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
            fieldId={`${idPrefix}-default`}
            labelHelp={defaultValueLabelHelp}
          >
            <SynNumberInputControl
              fieldId={`${idPrefix}-default`}
              ariaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
              placeholder={examples.defaultValue}
              value={rhfField.value}
              emptyValue={null}
              isDisabled={isDisabled}
              validated={fieldState.error ? 'error' : 'default'}
              onChange={(next) => {
                rhfField.onChange(next)
                commit()
              }}
              onBlur={rhfField.onBlur}
            />
            <FormFieldError error={fieldState.error} />
          </FormGroup>
        )}
      />
    )
  }

  if (field.type === FormFieldTypeEnum.DROPDOWN || field.type === FormFieldTypeEnum.MULTI_SELECT) {
    if (field.options.source === 'dynamic') {
      return (
        <FormGroup
          label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
          fieldId={`${idPrefix}-default`}
          labelHelp={defaultValueLabelHelp}
        >
          <FormFieldHintOrError hint={FORM_FIELD_BUILDER_INITIAL_ANSWER_DYNAMIC_UNAVAILABLE_HINT} />
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
        label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
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
