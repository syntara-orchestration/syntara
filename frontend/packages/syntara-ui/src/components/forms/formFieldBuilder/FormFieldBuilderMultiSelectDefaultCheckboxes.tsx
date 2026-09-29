import { Checkbox, FormGroup } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { useMemo } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../FormFieldError'
import { optionKey, type OptionScalarValue } from '../dynamicForm/synDynamicFormSelectHelpers'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'

type StaticOptionRow = {
  display_label: string
  value: OptionScalarValue
}

type FormFieldBuilderMultiSelectDefaultCheckboxesProps = {
  index: number
  idPrefix: string
  isDisabled?: boolean
  labelHelp?: ReactElement
}

function normalizeDefault(value: unknown): OptionScalarValue[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter(
    (entry): entry is OptionScalarValue =>
      typeof entry === 'string' || typeof entry === 'number' || typeof entry === 'boolean'
  )
}

function isValueSelected(selected: ReadonlyArray<OptionScalarValue>, value: OptionScalarValue): boolean {
  return selected.includes(value)
}

function toggleSelectedValue(
  selected: ReadonlyArray<OptionScalarValue>,
  value: OptionScalarValue,
  checked: boolean
): OptionScalarValue[] | null {
  if (checked) {
    if (isValueSelected(selected, value)) {
      return selected.length === 0 ? null : [...selected]
    }
    return [...selected, value]
  }
  const next = selected.filter((entry) => entry !== value)
  return next.length === 0 ? null : next
}

export function FormFieldBuilderMultiSelectDefaultCheckboxes({
  index,
  idPrefix,
  isDisabled,
  labelHelp,
}: Readonly<FormFieldBuilderMultiSelectDefaultCheckboxesProps>) {
  const commit = useFormFieldBuilderCommit()
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
      render={({ field: rhfField, fieldState }) => {
        const selected = normalizeDefault(rhfField.value)

        return (
          <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={labelHelp}>
            <div className={styles.defaultValueCheckboxList}>
              {options.map((option) => {
                const checkboxId = `${idPrefix}-default-${optionKey(option.value)}`
                return (
                  <Checkbox
                    key={checkboxId}
                    id={checkboxId}
                    label={option.display_label}
                    isChecked={isValueSelected(selected, option.value)}
                    isDisabled={isDisabled}
                    onChange={(_event, checked) => {
                      rhfField.onChange(toggleSelectedValue(selected, option.value, checked))
                      commit()
                    }}
                  />
                )
              })}
            </div>
            <FormFieldError error={fieldState.error} />
          </FormGroup>
        )
      }}
    />
  )
}
