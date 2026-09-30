import { Stack, StackItem } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'

type ExpressionHelpPopoverProps = {
  headerContent: string
  description: string
}

export function ExpressionHelpPopover({ headerContent, description }: ExpressionHelpPopoverProps) {
  return (
    <FieldHelpPopover
      headerContent={headerContent}
      helpText={
        <Stack hasGutter>
          <StackItem>{description}</StackItem>
          <StackItem>
            <strong>Form builder:</strong> Build conditions visually using a form interface with dropdowns and inputs.
          </StackItem>
          <StackItem>
            <strong>Freeform text:</strong> Write conditions directly as template expressions in the format{' '}
            <code>{'${variable operator value}'}</code>
          </StackItem>
        </Stack>
      }
    />
  )
}
