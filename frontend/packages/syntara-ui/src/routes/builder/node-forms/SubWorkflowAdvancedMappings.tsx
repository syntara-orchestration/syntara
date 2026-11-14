import {
  Alert,
  Content,
  ContentVariants,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { RhUiWarningIcon } from '@patternfly/react-icons'
import { useCallback, useMemo } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { TypeaheadSelect } from '../../access/TypeaheadSelect'
import { extractStepIdFromExpression, isStepConditional } from '../utils/conditionalStepDetection'
import type { SubWorkflowOutputField } from '../utils/subWorkflowOutputContract'

import { getStepOutputChoices, type OutputSourceOption } from './SubWorkflowOutputSourceOptions'

type Props = Readonly<{
  fields: SubWorkflowOutputField[]
  outputMapping: Record<string, string>
  triggerId: string
  triggerIndex: number
  isVersionView: boolean
  onMappingChange: (path: string, expression: string) => void
}>

function getFieldId(index: number) {
  return `subworkflow-output-${index}-advanced-expression`
}

function getSourceLabel(source: OutputSourceOption | undefined, isUnavailable: boolean): string | undefined {
  if (source) return `${source.stepName} · ${source.fieldName}`
  return isUnavailable ? 'Unavailable in current workflow' : undefined
}

export function SubWorkflowAdvancedMappings({
  fields,
  outputMapping,
  triggerId,
  triggerIndex,
  isVersionView,
  onMappingChange,
}: Props) {
  const activities = useWorkflowStore((state) => state.currentWorkflow?.workflow.activities ?? [])
  const edges = useWorkflowStore((state) => state.edges)
  const sourceOptions = useMemo(
    () => getStepOutputChoices(activities, edges, triggerId, triggerIndex),
    [activities, edges, triggerId, triggerIndex]
  )
  const isSourceConditional = useCallback(
    (expression: string): boolean => {
      const stepId = extractStepIdFromExpression(expression.trim())
      return stepId ? isStepConditional(stepId, activities, edges, [triggerId, `trigger-${triggerIndex}`]) : false
    },
    [activities, edges, triggerId, triggerIndex]
  )

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h4">Map output values</Title>
        <Content component={ContentVariants.p}>
          Required outputs are part of the child workflow’s return contract. If routing skips a required output’s source
          step, the child run fails. Optional outputs from skipped steps are omitted.
        </Content>
      </StackItem>
      {fields.length === 0 && (
        <StackItem>
          <Alert variant="info" isInline isPlain title="Add output fields to the schema above to map their values" />
        </StackItem>
      )}
      {fields.map((field, index) => {
        const expression = outputMapping[field.path] ?? ''
        const isConditional = expression ? isSourceConditional(expression) : false
        const sourceOption = sourceOptions.find((option) => option.expression === expression.trim())
        const isSourceUnavailable = Boolean(expression && !sourceOption)
        const isSourceTypeMismatch = Boolean(
          sourceOption &&
          field.type !== 'unknown' &&
          sourceOption.type !== 'unknown' &&
          sourceOption.type !== field.type
        )
        const label = field.path
        return (
          <StackItem key={field.path}>
            <FormGroup label={label} fieldId={getFieldId(index)} isRequired={field.required}>
              <TypeaheadSelect
                id={getFieldId(index)}
                ariaLabel={`Choose child output for ${field.path}`}
                options={sourceOptions.map((option) => ({
                  value: option.expression,
                  label: option.fieldName,
                  group: option.stepName,
                  description: option.sourceDescription,
                }))}
                selected={expression}
                selectedLabel={getSourceLabel(sourceOption, isSourceUnavailable)}
                onChange={(value) => onMappingChange(field.path, value)}
                placeholder="Choose a step output…"
                searchPromptThreshold={20}
                isRequired={field.required}
                isDisabled={isVersionView}
              />
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>Description: {field.description || 'No description'}</HelperTextItem>
                  {isConditional && (
                    <HelperTextItem variant={field.required ? 'warning' : 'indeterminate'} icon={<RhUiWarningIcon />}>
                      Source step may not execute on every workflow path.
                    </HelperTextItem>
                  )}
                  {isSourceUnavailable && (
                    <HelperTextItem variant="warning" icon={<RhUiWarningIcon />}>
                      This saved source is unavailable in the current workflow. Choose an existing child step output.
                    </HelperTextItem>
                  )}
                  {isSourceTypeMismatch && sourceOption && (
                    <HelperTextItem variant="warning" icon={<RhUiWarningIcon />}>
                      The declared type ({field.type}) differs from the selected source type ({sourceOption.type}).
                      Review the output schema.
                    </HelperTextItem>
                  )}
                </HelperText>
              </FormHelperText>
            </FormGroup>
          </StackItem>
        )
      })}
    </Stack>
  )
}
