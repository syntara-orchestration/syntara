import { FormGroup } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { useCallback, useMemo } from 'react'
import type { FieldError } from 'react-hook-form'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../FormFieldError'
import { OptionsTypeaheadSelect } from '../dynamicForm/OptionsTypeaheadSelect'
import { type OptionScalarValue } from '../dynamicForm/synDynamicFormSelectHelpers'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import {
  FORM_FIELD_BUILDER_INITIAL_ANSWER_DROPDOWN_PLACEHOLDER,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_OPTIONS_LIST_ARIA_LABEL,
} from './formFieldBuilderInitialAnswerCopy'

const STATIC_DEFAULT_NONE = '__form_field_builder_default_none__'

type StaticOptionRow = {
  display_label: string
  value: OptionScalarValue
}

type FormFieldBuilderDropdownDefaultSelectProps = {
  index: number
  idPrefix: string
  isDisabled?: boolean
  labelHelp?: ReactElement
}

type DropdownDefaultSelectControlProps = Readonly<{
  idPrefix: string
  labelHelp?: ReactElement
  isDisabled?: boolean
  options: ReadonlyArray<StaticOptionRow>
  currentDefault: OptionScalarValue | null | undefined
  onDefaultChange: (value: OptionScalarValue | null) => void
  fieldError?: FieldError
}>

function DropdownDefaultSelectControl({
  idPrefix,
  labelHelp,
  isDisabled,
  options,
  currentDefault,
  onDefaultChange,
  fieldError,
}: DropdownDefaultSelectControlProps) {
  const commit = useFormFieldBuilderCommit()
  const fieldId = `${idPrefix}-default`

  const selectOptions = useMemo(
    () => options.map((option) => ({ label: option.display_label, value: option.value })),
    [options]
  )

  const noneOption = useMemo(
    () => [
      {
        key: STATIC_DEFAULT_NONE,
        label: 'None',
        isSelected: currentDefault == null,
        onSelect: () => {
          onDefaultChange(null)
          commit()
        },
      },
    ],
    [commit, currentDefault, onDefaultChange]
  )

  const handleChange = useCallback(
    (value: unknown) => {
      if (value === '' || value === null || value === undefined) {
        onDefaultChange(null)
      } else if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        onDefaultChange(value)
      }
      commit()
    },
    [commit, onDefaultChange]
  )

  return (
    <FormGroup label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL} fieldId={fieldId} labelHelp={labelHelp}>
      <div className={currentDefault == null ? styles.staticDefaultTypeaheadPlaceholder : undefined}>
        <OptionsTypeaheadSelect
          fieldId={fieldId}
          ariaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
          listAriaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_OPTIONS_LIST_ARIA_LABEL}
          options={selectOptions}
          value={currentDefault ?? ''}
          onChange={handleChange}
          isMulti={false}
          isDisabled={isDisabled}
          emptyPlaceholder={FORM_FIELD_BUILDER_INITIAL_ANSWER_DROPDOWN_PLACEHOLDER}
          additionalOptions={noneOption}
        />
      </div>
      <FormFieldError error={fieldError} />
    </FormGroup>
  )
}

export function FormFieldBuilderDropdownDefaultSelect({
  index,
  idPrefix,
  isDisabled,
  labelHelp,
}: Readonly<FormFieldBuilderDropdownDefaultSelectProps>) {
  const { control } = useFormContext<FormDefinition>()

  const staticValues = useWatch({
    control,
    name: `fields.${index}.options.values`,
  }) as ReadonlyArray<StaticOptionRow> | undefined

  const options = useMemo(() => staticValues ?? [], [staticValues])

  return (
    <Controller
      control={control}
      name={`fields.${index}.default`}
      render={({ field: rhfField, fieldState }) => (
        <DropdownDefaultSelectControl
          idPrefix={idPrefix}
          labelHelp={labelHelp}
          isDisabled={isDisabled}
          options={options}
          currentDefault={rhfField.value as OptionScalarValue | null | undefined}
          onDefaultChange={rhfField.onChange}
          fieldError={fieldState.error}
        />
      )}
    />
  )
}
