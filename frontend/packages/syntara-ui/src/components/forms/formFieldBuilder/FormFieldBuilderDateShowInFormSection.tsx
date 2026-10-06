import { Checkbox, FormGroup, Stack, StackItem } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useFormContext, useWatch } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import {
  coerceDateValueShape,
  DATE_COMPONENT_NAMES,
  dateIncludesFromField,
  isSoleIncludedDateComponent,
  nextDateIncludes,
  normalizeDateDefaultForIncludes,
  type DateComponentName,
} from '../../../forms/dateFieldUtils'

import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

type FormFieldBuilderDateShowInFormSectionProps = Readonly<{
  index: number
  idPrefix: string
  isDisabled?: boolean
}>

const CHECKBOX_LABELS: Record<DateComponentName, string> = {
  date: 'Date',
  time: 'Time',
  timezone: 'Timezone',
}

export function FormFieldBuilderDateShowInFormSection({
  index,
  idPrefix,
  isDisabled,
}: FormFieldBuilderDateShowInFormSectionProps) {
  const commit = useFormFieldBuilderCommit()
  const { control, getValues, setValue } = useFormContext<FormDefinition>()
  const field = useWatch({ control, name: `fields.${index}` })

  if (field?.type !== FormFieldTypeEnum.DATE) {
    return null
  }

  const includes = dateIncludesFromField(field)
  const showInFormHelp = formFieldBuilderLabelHelp('dateShowInForm', 'Show in form')

  const applyIncludes = (next: Record<DateComponentName, boolean>) => {
    // Do not run the zod resolver on each toggle — time without timezone is an intermediate
    // builder state and would block updates before the user can finish selecting parts.
    setValue(`fields.${index}.include_date`, next.date, { shouldValidate: false, shouldDirty: true })
    setValue(`fields.${index}.include_time`, next.time, { shouldValidate: false, shouldDirty: true })
    setValue(`fields.${index}.include_timezone`, next.timezone, { shouldValidate: false, shouldDirty: true })

    const normalized = normalizeDateDefaultForIncludes(coerceDateValueShape(getValues(`fields.${index}.default`)), next)
    setValue(`fields.${index}.default`, normalized, { shouldValidate: false, shouldDirty: true })
    commit()
  }

  const toggle = (name: DateComponentName, checked: boolean) => {
    if (!checked && isSoleIncludedDateComponent(includes, name)) {
      return
    }

    const current = dateIncludesFromField(getValues(`fields.${index}`))
    const next = nextDateIncludes(current, name, checked)
    if (!next) {
      return
    }

    applyIncludes(next)
  }

  return (
    <FormGroup label="Show in form" fieldId={`${idPrefix}-show-in-form`} labelHelp={showInFormHelp} isRequired>
      <Stack hasGutter>
        {DATE_COMPONENT_NAMES.map((name) => (
          <StackItem key={name}>
            <Checkbox
              id={`${idPrefix}-include-${name}`}
              label={CHECKBOX_LABELS[name]}
              isChecked={includes[name]}
              isDisabled={isDisabled || isSoleIncludedDateComponent(includes, name)}
              onChange={(_event, checked) => toggle(name, checked)}
            />
          </StackItem>
        ))}
      </Stack>
    </FormGroup>
  )
}
