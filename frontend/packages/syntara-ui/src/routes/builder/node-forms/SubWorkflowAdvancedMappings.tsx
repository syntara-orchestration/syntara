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
  TextInput,
  Title,
} from '@patternfly/react-core'
import { useCallback } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { extractStepIdFromExpression, isStepConditional } from '../utils/conditionalStepDetection'
import type { SubWorkflowOutputField } from '../utils/subWorkflowOutputContract'

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
  const isSourceConditional = useCallback(
    (expression: string): boolean => {
      const stepId = extractStepIdFromExpression(expression)
      return stepId ? isStepConditional(stepId, activities, edges, [triggerId, `trigger-${triggerIndex}`]) : false
    },
    [activities, edges, triggerId, triggerIndex]
  )

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h4">Map output values</Title>
        <Content component={ContentVariants.p}>
          Choose the child step output that supplies each declared field. The value is available if that step runs.
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
        const label = `${field.path} (${field.type})${field.required ? ' — Required' : ' — Optional'}`
        return (
          <StackItem key={field.path}>
            <FormGroup label={label} fieldId={getFieldId(index)}>
              <TextInput
                id={getFieldId(index)}
                value={expression}
                onChange={(_event, value) => onMappingChange(field.path, value)}
                placeholder="e.g., ${deploy_app.artifact_url}"
                isDisabled={isVersionView}
              />
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>Description: {field.description || 'No description'}</HelperTextItem>
                  {isConditional && (
                    <HelperTextItem variant={field.required ? 'warning' : 'indeterminate'}>
                      Source step may not execute on every workflow path.
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
