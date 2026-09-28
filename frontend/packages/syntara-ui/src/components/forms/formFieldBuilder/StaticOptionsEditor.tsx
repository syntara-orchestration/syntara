import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { restrictToVerticalAxis } from '@dnd-kit/modifiers'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Button, Stack, StackItem, Title } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import type { FormDefinition } from '@syntara/contracts'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { FORM_STATIC_OPTIONS_MAX_LENGTH, FormFieldTypeEnum } from '../../../forms'

import { createDefaultStaticOption } from './createDefaultField'
import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { StaticOptionRow } from './StaticOptionRow'

type StaticOptionsEditorProps = {
  fieldIndex: number
  isDisabled?: boolean
}

export function StaticOptionsEditor({ fieldIndex, isDisabled }: Readonly<StaticOptionsEditorProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control, getValues, setValue } = useFormContext<FormDefinition>()
  const fieldLabel = useWatch({ control, name: `fields.${fieldIndex}.label` }) ?? `Field ${fieldIndex + 1}`
  const { fields, append, move, remove } = useFieldArray({
    control,
    name: `fields.${fieldIndex}.options.values`,
  })

  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor))
  const atMax = fields.length >= FORM_STATIC_OPTIONS_MAX_LENGTH

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id) {
      const oldIndex = fields.findIndex((f) => f.id === active.id)
      const newIndex = fields.findIndex((f) => f.id === over.id)
      if (oldIndex !== -1 && newIndex !== -1) {
        move(oldIndex, newIndex)
        commit()
      }
    }
  }

  return (
    <div className={styles.staticOptionsSection}>
      <Title headingLevel="h4" size="md" className={styles.staticOptionsHeading}>
        Static options
      </Title>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        modifiers={[restrictToVerticalAxis]}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
          <Stack hasGutter>
            {fields.map((option, optionIndex) => (
              <StackItem key={option.id}>
                <StaticOptionRow
                  fieldIndex={fieldIndex}
                  fieldLabel={fieldLabel}
                  optionIndex={optionIndex}
                  optionArrayId={option.id}
                  isDisabled={isDisabled}
                  canRemove={fields.length > 1}
                  onRemove={() => {
                    const values = getValues(`fields.${fieldIndex}.options.values`) ?? []
                    const removedValue = values[optionIndex]?.value
                    remove(optionIndex)
                    const field = getValues(`fields.${fieldIndex}`)
                    if (removedValue !== undefined) {
                      if (field.type === FormFieldTypeEnum.MULTI_SELECT && Array.isArray(field.default)) {
                        setValue(
                          `fields.${fieldIndex}.default`,
                          field.default.filter((entry) => entry !== removedValue),
                          { shouldValidate: true }
                        )
                      } else if (field.type === FormFieldTypeEnum.DROPDOWN && field.default === removedValue) {
                        setValue(`fields.${fieldIndex}.default`, null, { shouldValidate: true })
                      }
                    }
                    commit()
                  }}
                />
              </StackItem>
            ))}
          </Stack>
        </SortableContext>
      </DndContext>
      <Button
        className={styles.staticOptionsAdd}
        variant="link"
        icon={<RhUiAddIcon />}
        isDisabled={isDisabled || atMax}
        onClick={() => {
          const values = getValues(`fields.${fieldIndex}.options.values`) ?? []
          const takenValues = values.map((entry) => String(entry.value))
          append(createDefaultStaticOption(values.length, takenValues))
          commit()
        }}
      >
        Add option
      </Button>
    </div>
  )
}
