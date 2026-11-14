import { Alert, Button, StackItem } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useMemo } from 'react'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { extractStepIdFromExpression, isStepConditional } from '../utils/conditionalStepDetection'

import { getStepOutputChoices } from './SubWorkflowOutputSourceOptions'
import { SubWorkflowSimpleOutputFieldCard } from './SubWorkflowSimpleOutputFieldCard'
import type { TriggerFormData } from './triggerFormSchema'

type OutputField = NonNullable<TriggerFormData['outputFields']>[number]

export function SubWorkflowSimpleOutputFields({
  triggerId,
  triggerIndex,
  isVersionView,
  onRowsChange,
}: Readonly<{
  triggerId: string
  triggerIndex: number
  isVersionView: boolean
  onRowsChange: (rows: OutputField[]) => void
}>) {
  const activities = useWorkflowStore((state) => state.currentWorkflow?.workflow.activities ?? [])
  const edges = useWorkflowStore((state) => state.edges)
  const {
    control,
    formState: { errors },
  } = useFormContext<TriggerFormData>()
  const { fields, append: appendOutput, remove: removeOutput } = useFieldArray({ control, name: 'outputFields' })
  const watchedRows = useWatch({ control, name: 'outputFields' })
  const outputRows = useMemo(() => watchedRows ?? [], [watchedRows])
  const sourceOptions = useMemo(
    () => getStepOutputChoices(activities, edges, triggerId, triggerIndex),
    [activities, edges, triggerId, triggerIndex]
  )

  const isSourceConditional = (expression: string): boolean => {
    const stepId = extractStepIdFromExpression(expression.trim())
    return stepId ? isStepConditional(stepId, activities, edges, [triggerId, `trigger-${triggerIndex}`]) : false
  }

  const handleAddField = () => {
    const newField: OutputField = { path: '', type: 'unknown', required: false, description: '', expression: '' }
    appendOutput(newField)
    onRowsChange([...outputRows, newField])
  }

  const handleRemoveField = (index: number) => {
    removeOutput(index)
    onRowsChange(outputRows.filter((_row, rowIndex) => rowIndex !== index))
  }

  const handleRowChange = (index: number, nextRow: OutputField) => {
    onRowsChange(outputRows.map((row, rowIndex) => (rowIndex === index ? nextRow : row)))
  }

  return (
    <>
      {fields.length === 0 && (
        <StackItem>
          <Alert variant="info" isInline isPlain title="No outputs configured">
            Add one to expose a child step value to the parent.
          </Alert>
        </StackItem>
      )}
      {fields.map((field, index) => {
        const row = outputRows[index]
        if (!row) return null
        return (
          <SubWorkflowSimpleOutputFieldCard
            key={field.id}
            index={index}
            row={row}
            sourceOptions={sourceOptions}
            isVersionView={isVersionView}
            isSourceConditional={isSourceConditional}
            outputNameError={errors.outputFields?.[index]?.path?.message}
            onRowChange={(nextRow) => handleRowChange(index, nextRow)}
            onRemove={() => handleRemoveField(index)}
          />
        )
      })}
      {!isVersionView && (
        <StackItem>
          <Button variant="link" icon={<RhUiAddIcon />} onClick={handleAddField} isInline>
            Add output field
          </Button>
        </StackItem>
      )}
    </>
  )
}
