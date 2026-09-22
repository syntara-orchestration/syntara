import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button, Card, CardBody, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiGripVerticalFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { FormDefinition, FormField } from '@syntara/contracts'
import { useId, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { labelToValueName, slugifyLabelToValueNameBase, type FormFieldType } from '../../../forms'

import { replaceFieldType } from './createDefaultField'
import styles from './formFieldBuilder.module.css'
import { FormFieldBuilderCardFields } from './FormFieldBuilderCardFields'
import { FormFieldBuilderCardHeaderLabel } from './FormFieldBuilderCardHeaderLabel'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'

type FormFieldBuilderCardProps = {
  fieldArrayId: string
  index: number
  canRemove: boolean
  isDisabled?: boolean
  onRemove: () => void
}

export function FormFieldBuilderCard({
  fieldArrayId,
  index,
  canRemove,
  isDisabled,
  onRemove,
}: Readonly<FormFieldBuilderCardProps>) {
  const idPrefix = useId()
  const contentId = `${idPrefix}-field-content`
  const [isExpanded, setIsExpanded] = useState(true)
  const commit = useFormFieldBuilderCommit()
  const { control, setValue, getValues, clearErrors } = useFormContext<FormDefinition>()
  const field = useWatch({ control, name: `fields.${index}` }) as FormField | undefined

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: fieldArrayId,
    disabled: isDisabled,
  })

  const sortableStyle = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  if (!field) {
    return null
  }

  const otherValueNames = (getValues('fields') ?? []).map((f, i) => (i === index ? '' : f.value_name)).filter(Boolean)
  const autoValueName = labelToValueName(field.label, otherValueNames)
  const valueNameLooksGenerated =
    field.value_name === autoValueName || field.value_name === slugifyLabelToValueNameBase(field.label)

  const handleLabelChange = (nextLabel: string) => {
    const current = getValues(`fields.${index}`)
    const otherNames = (getValues('fields') ?? []).map((f, i) => (i === index ? '' : f.value_name)).filter(Boolean)
    const previousAuto = labelToValueName(current.label, otherNames)
    const shouldAutoRename =
      current.value_name === '' ||
      current.value_name === previousAuto ||
      current.value_name === slugifyLabelToValueNameBase(current.label)

    setValue(`fields.${index}.label`, nextLabel, { shouldValidate: false })
    if (shouldAutoRename) {
      setValue(`fields.${index}.value_name`, labelToValueName(nextLabel, otherNames), { shouldValidate: false })
    }
    commit()
  }

  const handleTypeChange = (newType: FormFieldType) => {
    const current = getValues(`fields.${index}`)
    const names = (getValues('fields') ?? []).map((f) => f.value_name)
    setValue(`fields.${index}`, replaceFieldType(current, newType, names), { shouldValidate: false })
    clearErrors(`fields.${index}`)
    commit()
  }

  return (
    <div ref={setNodeRef} style={sortableStyle} className={isDragging ? styles.dragging : undefined}>
      <Flex className={styles.fieldRow} gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsFlexStart' }}>
        <FlexItem>
          <Button
            variant="plain"
            className={styles.dragHandle}
            aria-label={`Reorder field ${index + 1}`}
            isDisabled={isDisabled}
            {...(isDisabled ? {} : listeners)}
            {...(isDisabled ? {} : attributes)}
          >
            <RhUiGripVerticalFillIcon />
          </Button>
        </FlexItem>
        <FlexItem grow={{ default: 'grow' }}>
          <Card className={styles.fieldCard} isPlain>
            <CardBody className={styles.fieldCardBody}>
              {canRemove && (
                <div className={styles.headerActions}>
                  <Button
                    variant="plain"
                    aria-label={`Remove field ${index + 1}`}
                    isDisabled={isDisabled}
                    onClick={onRemove}
                  >
                    <RhUiTrashIcon />
                  </Button>
                </div>
              )}
              <Stack hasGutter>
                <StackItem className={styles.headerRow}>
                  <Flex alignItems={{ default: 'alignItemsFlexStart' }} gap={{ default: 'gapSm' }}>
                    <FlexItem className={styles.headerToggle}>
                      <Button
                        variant="plain"
                        className={styles.toggleButton}
                        aria-expanded={isExpanded}
                        aria-controls={contentId}
                        onClick={() => setIsExpanded((expanded) => !expanded)}
                        aria-label={`${isExpanded ? 'Collapse' : 'Expand'} field ${index + 1}`}
                        isDisabled={isDisabled}
                      >
                        <RhUiCaretDownIcon className={styles.toggleIcon} />
                      </Button>
                    </FlexItem>
                    <FlexItem grow={{ default: 'grow' }} className={styles.headerLabelField}>
                      <FormFieldBuilderCardHeaderLabel
                        index={index}
                        idPrefix={idPrefix}
                        isDisabled={isDisabled}
                        onLabelChange={handleLabelChange}
                      />
                    </FlexItem>
                  </Flex>
                </StackItem>
                {isExpanded && (
                  <StackItem id={contentId}>
                    <FormFieldBuilderCardFields
                      index={index}
                      field={field}
                      idPrefix={idPrefix}
                      isDisabled={isDisabled}
                      valueNameLooksGenerated={valueNameLooksGenerated}
                      onTypeChange={handleTypeChange}
                    />
                  </StackItem>
                )}
              </Stack>
            </CardBody>
          </Card>
        </FlexItem>
      </Flex>
    </div>
  )
}
