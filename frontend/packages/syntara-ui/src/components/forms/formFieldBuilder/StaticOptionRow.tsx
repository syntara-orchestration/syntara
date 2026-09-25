import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button, Flex, FlexItem, FormGroup, Stack, StackItem, TextInput } from '@patternfly/react-core'
import { RhUiGripVerticalFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { FormDefinition } from '@syntara/contracts'
import { useId } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { labelToValueName, slugifyLabelToValueNameBase } from '../../../forms'
import { FormFieldError } from '../../FormFieldError'
import { SynTextField } from '../SynTextField'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

type StaticOptionRowProps = {
  fieldIndex: number
  optionIndex: number
  optionArrayId: string
  isDisabled?: boolean
  canRemove: boolean
  onRemove: () => void
}

function otherOptionValues(values: ReadonlyArray<{ value: string | number | boolean }>, optionIndex: number): string[] {
  return values
    .map((entry, index) => (index === optionIndex ? '' : String(entry.value)))
    .filter((entry) => entry.length > 0)
}

export function StaticOptionRow({
  fieldIndex,
  optionIndex,
  optionArrayId,
  isDisabled,
  canRemove,
  onRemove,
}: Readonly<StaticOptionRowProps>) {
  const idPrefix = useId()
  const commit = useFormFieldBuilderCommit()
  const { control, setValue, getValues } = useFormContext<FormDefinition>()

  const optionValues = useWatch({
    control,
    name: `fields.${fieldIndex}.options.values`,
  }) as ReadonlyArray<{ display_label: string; value: string }> | undefined

  const displayLabel = optionValues?.[optionIndex]?.display_label ?? ''
  const optionValue = optionValues?.[optionIndex]?.value ?? ''
  const siblings = optionValues ?? []
  const otherValues = otherOptionValues(siblings, optionIndex)
  const autoValue = labelToValueName(displayLabel, otherValues)
  const valueNameLooksGenerated = optionValue === autoValue || optionValue === slugifyLabelToValueNameBase(displayLabel)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: optionArrayId,
    disabled: isDisabled,
  })

  const sortableStyle = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div ref={setNodeRef} style={sortableStyle} className={isDragging ? styles.staticOptionDragging : undefined}>
      <Flex
        className={styles.staticOptionRow}
        gap={{ default: 'gapSm' }}
        alignItems={{ default: 'alignItemsFlexStart' }}
      >
        <FlexItem>
          <Button
            variant="plain"
            className={styles.staticOptionDragHandle}
            aria-label={`Reorder option ${optionIndex + 1}`}
            isDisabled={isDisabled}
            {...(isDisabled ? {} : listeners)}
            {...(isDisabled ? {} : attributes)}
          >
            <RhUiGripVerticalFillIcon />
          </Button>
        </FlexItem>
        <FlexItem grow={{ default: 'grow' }} className={styles.staticOptionFieldsColumn}>
          <div className={styles.staticOptionFields}>
            {canRemove && (
              <div className={styles.staticOptionRemove}>
                <Button
                  variant="plain"
                  aria-label={`Remove option ${optionIndex + 1}`}
                  isDisabled={isDisabled}
                  onClick={onRemove}
                >
                  <RhUiTrashIcon />
                </Button>
              </div>
            )}
            <Stack hasGutter>
              <StackItem>
                <Controller
                  control={control}
                  name={`fields.${fieldIndex}.options.values.${optionIndex}.display_label`}
                  render={({ field: rhfField, fieldState }) => (
                    <FormGroup
                      label="Display label"
                      fieldId={`${idPrefix}-display-label`}
                      isRequired
                      labelHelp={formFieldBuilderLabelHelp('optionDisplayLabel', 'Display label')}
                    >
                      <TextInput
                        id={`${idPrefix}-display-label`}
                        value={rhfField.value ?? ''}
                        validated={fieldState.error ? 'error' : 'default'}
                        isDisabled={isDisabled}
                        onChange={(_event, nextLabel) => {
                          const values = getValues(`fields.${fieldIndex}.options.values`) ?? []
                          const current = values[optionIndex]
                          if (!current) {
                            return
                          }
                          const taken = otherOptionValues(values, optionIndex)
                          const previousAuto = labelToValueName(current.display_label, taken)
                          const shouldAutoRename =
                            current.value === '' ||
                            current.value === previousAuto ||
                            current.value === slugifyLabelToValueNameBase(current.display_label)

                          rhfField.onChange(nextLabel)
                          if (shouldAutoRename) {
                            setValue(
                              `fields.${fieldIndex}.options.values.${optionIndex}.value`,
                              labelToValueName(nextLabel, taken),
                              { shouldValidate: false }
                            )
                          }
                          commit()
                        }}
                        onBlur={rhfField.onBlur}
                      />
                      <FormFieldError error={fieldState.error} />
                    </FormGroup>
                  )}
                />
              </StackItem>
              <StackItem>
                <SynTextField
                  name={`fields.${fieldIndex}.options.values.${optionIndex}.value`}
                  control={control}
                  label="Value name"
                  fieldId={`${idPrefix}-value-name`}
                  isRequired
                  isDisabled={isDisabled}
                  labelHelp={formFieldBuilderLabelHelp('optionValueName', 'Value name')}
                  hint={valueNameLooksGenerated ? 'Generated from the display label above' : undefined}
                  onValueChange={commit}
                />
              </StackItem>
            </Stack>
          </div>
        </FlexItem>
      </Flex>
    </div>
  )
}
