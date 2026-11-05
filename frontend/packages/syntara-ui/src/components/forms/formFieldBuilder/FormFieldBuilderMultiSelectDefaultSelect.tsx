import { FormGroup } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { useMemo } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../FormFieldError'
import { OptionsTypeaheadSelect } from '../dynamicForm/OptionsTypeaheadSelect'
import { type OptionScalarValue } from '../dynamicForm/synDynamicFormSelectHelpers'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import {
  FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_MULTI_SELECT_PLACEHOLDER,
  FORM_FIELD_BUILDER_INITIAL_ANSWER_OPTIONS_LIST_ARIA_LABEL,
} from './formFieldBuilderInitialAnswerCopy'

type StaticOptionRow = {
  display_label: string
  value: OptionScalarValue
}

type FormFieldBuilderMultiSelectDefaultSelectProps = {
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

export function FormFieldBuilderMultiSelectDefaultSelect({
  index,
  idPrefix,
  isDisabled,
  labelHelp,
}: Readonly<FormFieldBuilderMultiSelectDefaultSelectProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control } = useFormContext<FormDefinition>()

  const staticValues = useWatch({
    control,
    name: `fields.${index}.options.values`,
  }) as ReadonlyArray<StaticOptionRow> | undefined

  const options = useMemo(() => staticValues ?? [], [staticValues])
  const selectOptions = useMemo(
    () => options.map((option) => ({ label: option.display_label, value: option.value })),
    [options]
  )

  const fieldId = `${idPrefix}-default`

  return (
    <Controller
      control={control}
      name={`fields.${index}.default`}
      render={({ field: rhfField, fieldState }) => {
        const selected = normalizeDefault(rhfField.value)

        return (
          <FormGroup
            label={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
            fieldId={fieldId}
            labelHelp={labelHelp}
          >
            <OptionsTypeaheadSelect
              fieldId={fieldId}
              ariaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}
              listAriaLabel={FORM_FIELD_BUILDER_INITIAL_ANSWER_OPTIONS_LIST_ARIA_LABEL}
              options={selectOptions}
              value={selected}
              onChange={(value) => {
                if (!Array.isArray(value)) {
                  rhfField.onChange(null)
                  commit()
                  return
                }
                const next = value.filter(
                  (entry): entry is OptionScalarValue =>
                    typeof entry === 'string' || typeof entry === 'number' || typeof entry === 'boolean'
                )
                rhfField.onChange(next.length === 0 ? null : next)
                commit()
              }}
              isMulti
              isDisabled={isDisabled}
              emptyPlaceholder={FORM_FIELD_BUILDER_INITIAL_ANSWER_MULTI_SELECT_PLACEHOLDER}
            />
            <FormFieldError error={fieldState.error} />
          </FormGroup>
        )
      }}
    />
  )
}
