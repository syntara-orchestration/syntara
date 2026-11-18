import { Checkbox, FormGroup, FormHelperText, HelperText, HelperTextItem, List, ListItem } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { FormDefinition } from '@syntara/contracts'
import { useController, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldTypeEnum, formDefinitionInlineFieldMessage } from '../../../forms'
import {
  coerceDateValueShape,
  DATE_COMPONENT_NAMES,
  dateIncludesFromField,
  isDateFieldDateAndTimezoneWithoutTime,
  isSoleIncludedDateComponent,
  isUnsupportedRfc3339DateFieldCombination,
  nextDateIncludes,
  normalizeDateDefaultForIncludes,
  type DateComponentName,
} from '../../../forms/dateFieldUtils'
import {
  DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
  normalizeDateFieldCombinationMessage,
} from '../../../forms/dateFieldValidationMessages'

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

function resolvedFieldMessage(error: { message?: unknown } | undefined): string | undefined {
  return typeof error?.message === 'string' && error.message.length > 0 ? error.message : undefined
}

function isDateFieldCombinationErrorMessage(message: string | undefined): boolean {
  if (message == null) {
    return false
  }
  const inline = formDefinitionInlineFieldMessage(message)
  if (inline === DATE_FIELD_RFC3339_COMBINATION_MESSAGE) {
    return true
  }
  return normalizeDateFieldCombinationMessage(message) != null
}

/** Match strict-mode highlighting: combo issues are about which includes are checked, not zod path. */
function isShowInFormCheckboxInvalidForUnsupportedCombination(
  name: DateComponentName,
  options: Readonly<{
    includes: Record<DateComponentName, boolean>
    dateAndTimezoneWithoutTime: boolean
  }>
): boolean {
  if (options.dateAndTimezoneWithoutTime) {
    return name === 'time'
  }
  return options.includes[name]
}

function isShowInFormCheckboxInvalid(
  name: DateComponentName,
  options: Readonly<{
    showCombinationError: boolean
    includes: Record<DateComponentName, boolean>
    unsupportedCombination: boolean
    dateAndTimezoneWithoutTime: boolean
    isDraftBuilder: boolean
    resolvedIncludeTimeMessage: string | undefined
    resolvedIncludeDateMessage: string | undefined
  }>
): boolean {
  if (!options.showCombinationError) {
    return false
  }

  const resolvedServerMessage = options.resolvedIncludeTimeMessage ?? options.resolvedIncludeDateMessage
  const isComboServerMessage = isDateFieldCombinationErrorMessage(resolvedServerMessage)

  if (options.unsupportedCombination && (isComboServerMessage || !options.isDraftBuilder)) {
    return isShowInFormCheckboxInvalidForUnsupportedCombination(name, options)
  }

  if (options.resolvedIncludeTimeMessage != null && name === 'time') {
    return true
  }
  if (options.resolvedIncludeDateMessage != null && name === 'date') {
    return true
  }

  return false
}

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
  const {
    fieldState: { error: includeDateFieldError },
  } = useController({
    control,
    name: `fields.${index}.include_date`,
  })
  const field = useWatch({ control, name: `fields.${index}` })

  if (field?.type !== FormFieldTypeEnum.DATE) {
    return null
  }

  const includes = dateIncludesFromField(field)
  const dateAndTimezoneWithoutTime = isDateFieldDateAndTimezoneWithoutTime(field)
  const unsupportedCombination = isUnsupportedRfc3339DateFieldCombination(field)
  const resolvedIncludeTimeMessage = resolvedFieldMessage(includeTimeFieldError)
  const resolvedIncludeDateMessage = resolvedFieldMessage(includeDateFieldError)
  const resolvedServerMessageRaw = resolvedIncludeTimeMessage ?? resolvedIncludeDateMessage
  const resolvedServerMessage =
    resolvedServerMessageRaw != null ? formDefinitionInlineFieldMessage(resolvedServerMessageRaw) : undefined

  const showCombinationError = resolvedServerMessage != null || (!isDraftBuilder && unsupportedCombination)

  const combinationErrorMessage =
    resolvedServerMessage ?? (unsupportedCombination ? DATE_FIELD_RFC3339_COMBINATION_MESSAGE : undefined)

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
      <fieldset
        className={styles.showInFormFieldset}
        aria-labelledby={showInFormGroupLabelId}
        aria-describedby={showCombinationError ? showInFormErrorId : undefined}
        disabled={isDisabled}
      >
        <List isPlain>
          {DATE_COMPONENT_NAMES.map((name) => {
            const checkboxInvalid = isShowInFormCheckboxInvalid(name, {
              showCombinationError,
              includes,
              unsupportedCombination,
              dateAndTimezoneWithoutTime,
              isDraftBuilder,
              resolvedIncludeTimeMessage,
              resolvedIncludeDateMessage,
            })
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
      </fieldset>
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
