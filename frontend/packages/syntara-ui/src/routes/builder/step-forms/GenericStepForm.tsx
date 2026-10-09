import { Button, Content, ContentVariants, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'

import type { BaseStepFormProps } from '../registry/StepRegistry'

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
type GenericStepFormData = {
  // No data needed - this form just triggers the node to be added
}

/**
 * Form component for Generic placeholder nodes
 * This is a minimal form that immediately succeeds to add the generic node to canvas
 */
export function GenericStepForm({ onSubmit, onCancel, submitButtonText }: BaseStepFormProps<GenericStepFormData>) {
  // Automatically submit when form is shown
  // This creates the generic node on canvas immediately
  const handleSubmit = () => {
    onSubmit({})
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component={ContentVariants.p}>
          A generic placeholder step will be added to the canvas. Click on it to configure the step type.
        </Content>
      </StackItem>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapSm' }}>
          <FlexItem>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </FlexItem>
          <FlexItem>
            <Button variant="primary" onClick={handleSubmit}>
              {submitButtonText ?? 'Add Generic Step'}
            </Button>
          </FlexItem>
        </Flex>
      </StackItem>
    </Stack>
  )
}
