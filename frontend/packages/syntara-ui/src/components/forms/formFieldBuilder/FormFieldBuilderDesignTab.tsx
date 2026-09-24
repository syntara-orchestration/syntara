import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { restrictToVerticalAxis } from '@dnd-kit/modifiers'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Alert, Button, Content, ContentVariants, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiGripVerticalFillIcon } from '@patternfly/react-icons'
import type { FormDefinition } from '@syntara/contracts'
import { useMemo, useState } from 'react'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import {
  FORM_DEFINITION_MAX_FIELDS,
  FORM_DEFINITION_MIN_FIELDS,
  FormFieldTypeEnum,
  safeParseFormDefinition,
} from '../../../forms'
import { SynConfirmationDialog } from '../../dialogs/SynConfirmationDialog'

import { createDefaultField } from './createDefaultField'
import styles from './formFieldBuilder.module.css'
import { FormFieldBuilderCard } from './FormFieldBuilderCard'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'

type FormFieldBuilderDesignTabProps = {
  isDisabled?: boolean
}

export function FormFieldBuilderDesignTab({ isDisabled }: Readonly<FormFieldBuilderDesignTabProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control, getValues } = useFormContext<FormDefinition>()
  const watchedFields = useWatch({ control, name: 'fields' })
  const { fields, append, remove, move } = useFieldArray({ control, name: 'fields' })
  const [activeId, setActiveId] = useState<string | null>(null)
  const [pendingRemoveIndex, setPendingRemoveIndex] = useState<number | null>(null)

  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor))

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveId(null)
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

  const activeField = useMemo(() => (activeId ? fields.find((f) => f.id === activeId) : null), [activeId, fields])

  const handleAddField = () => {
    if (fields.length >= FORM_DEFINITION_MAX_FIELDS) {
      return
    }
    const names = (getValues('fields') ?? []).map((f) => f.value_name)
    append(createDefaultField(FormFieldTypeEnum.TEXT, names))
    commit()
  }

  const atMaxFields = fields.length >= FORM_DEFINITION_MAX_FIELDS

  const pendingRemoveLabel =
    pendingRemoveIndex !== null ? fields[pendingRemoveIndex]?.label?.trim() || 'Field label' : ''

  const definitionValidation = useMemo(() => safeParseFormDefinition({ fields: watchedFields }), [watchedFields])

  return (
    <Stack hasGutter className={styles.designTab}>
      {!definitionValidation.success && (
        <StackItem>
          <Alert
            variant="warning"
            title="Fix validation errors before changes are saved to the parent form."
            isInline
          />
        </StackItem>
      )}
      <StackItem>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis]}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
            <Stack hasGutter>
              {fields.map((field, index) => (
                <StackItem key={field.id}>
                  <FormFieldBuilderCard
                    fieldArrayId={field.id}
                    index={index}
                    canRemove={fields.length > FORM_DEFINITION_MIN_FIELDS}
                    isDisabled={isDisabled}
                    onRemove={() => setPendingRemoveIndex(index)}
                  />
                </StackItem>
              ))}
            </Stack>
          </SortableContext>
          <DragOverlay>
            {activeField && (
              <div className={styles.dragOverlay}>
                <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                  <FlexItem>
                    <RhUiGripVerticalFillIcon />
                  </FlexItem>
                  <FlexItem grow={{ default: 'grow' }}>{activeField.label.trim() || 'Field label'}</FlexItem>
                </Flex>
              </div>
            )}
          </DragOverlay>
        </DndContext>
      </StackItem>
      <StackItem>
        <Button variant="link" icon={<RhUiAddIcon />} isDisabled={isDisabled || atMaxFields} onClick={handleAddField}>
          Add field
        </Button>
      </StackItem>
      <SynConfirmationDialog
        isOpen={pendingRemoveIndex !== null}
        onClose={() => setPendingRemoveIndex(null)}
        onConfirm={() => {
          if (pendingRemoveIndex === null) {
            return
          }
          remove(pendingRemoveIndex)
          commit()
          setPendingRemoveIndex(null)
        }}
        title="Remove field?"
        confirmLabel="Remove field"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        <Content component={ContentVariants.p}>
          The field <strong>{pendingRemoveLabel}</strong> will be removed. This cannot be undone.
        </Content>
      </SynConfirmationDialog>
    </Stack>
  )
}
