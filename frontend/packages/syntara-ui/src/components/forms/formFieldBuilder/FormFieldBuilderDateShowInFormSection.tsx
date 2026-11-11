import { Checkbox, FormGroup, FormHelperText, HelperText, HelperTextItem, List, ListItem } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { FormDefinition } from '@syntara/contracts'
import { useController, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import {
  coerceDateValueShape,
  DATE_COMPONENT_NAMES,
  dateIncludesFromField,
  isDateFieldDateAndTimezoneWithoutTime,
  isSoleIncludedDateComponent,
  nextDateIncludes,
  normalizeDateDefaultForIncludes,
  type DateComponentName,
} from '../../../forms/dateFieldUtils'
import { DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE } from '../../../forms/dateFieldValidationMessages'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { useFormFieldBuilderDraftMode } from './formFieldBuilderDraftModeContext'
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

const SHOW_IN_FORM_LABEL = 'Show in form'

export function FormFieldBuilderDateShowInFormSection({
  index,
  idPrefix,
  isDisabled,
}: FormFieldBuilderDateShowInFormSectionProps) {
  const commit = useFormFieldBuilderCommit()
  const isDraftBuilder = useFormFieldBuilderDraftMode()
  const { control, getValues, setValue } = useFormContext<FormDefinition>()
  const {
    fieldState: { error: includeTimeFieldError },
  } = useController({
    control,
    name: `fields.${index}.include_time`,
  })
  const field = useWatch({ control, name: `fields.${index}` })
  const resolvedIncludeTimeMessage =
    typeof includeTimeFieldError?.message === 'string' && includeTimeFieldError.message.length > 0
      ? includeTimeFieldError.message
      : undefined

  if (field?.type !== FormFieldTypeEnum.DATE) {
    return null
  }

  const includes = dateIncludesFromField(field)
  const dateAndTimezoneWithoutTime = isDateFieldDateAndTimezoneWithoutTime(field)
  const showCombinationError =
    (typeof resolvedIncludeTimeMessage === 'string' && resolvedIncludeTimeMessage.length > 0) ||
    (!isDraftBuilder && dateAndTimezoneWithoutTime)
  const combinationErrorMessage = resolvedIncludeTimeMessage ?? DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE

  const showInFormFieldId = `${idPrefix}-show-in-form`
  const showInFormGroupLabelId = `${showInFormFieldId}-label`
  const showInFormErrorId = `${showInFormFieldId}-error`
  const showInFormHelp = formFieldBuilderLabelHelp('dateShowInForm', SHOW_IN_FORM_LABEL)

  const applyIncludes = (next: Record<DateComponentName, boolean>) => {
    // Do not run the zod resolver on each toggle — incomplete date combinations are allowed
    // in the builder and are enforced on canvas validation / run / publish instead.
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
    <FormGroup
      label={<span id={showInFormGroupLabelId}>{SHOW_IN_FORM_LABEL}</span>}
      fieldId={showInFormFieldId}
      labelHelp={showInFormHelp}
      isRequired
      className={showCombinationError ? styles.formGroupLabelError : undefined}
    >
      <div
        role="group"
        aria-labelledby={showInFormGroupLabelId}
        aria-describedby={showCombinationError ? showInFormErrorId : undefined}
      >
        <List isPlain>
          {DATE_COMPONENT_NAMES.map((name) => {
            const checkboxInvalid = showCombinationError && name === 'time'
            return (
              <ListItem key={name}>
                <Checkbox
                  id={`${idPrefix}-include-${name}`}
                  label={CHECKBOX_LABELS[name]}
                  isChecked={includes[name]}
                  isDisabled={isDisabled || isSoleIncludedDateComponent(includes, name)}
                  isValid={checkboxInvalid ? false : undefined}
                  aria-describedby={checkboxInvalid ? showInFormErrorId : undefined}
                  onChange={(_event, checked) => toggle(name, checked)}
                />
              </ListItem>
            )
          })}
        </List>
      </div>
      {showCombinationError ? (
        <FormHelperText>
          <HelperText isLiveRegion>
            <HelperTextItem id={showInFormErrorId} icon={<RhUiErrorIcon />} variant="error">
              {combinationErrorMessage}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      ) : null}
    </FormGroup>
  )
}
