import { Stack, StackItem } from '@patternfly/react-core'

import { EXPRESSION_MODE_LABELS } from '../../../../components/expressions/expressionBuilderLabels'
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
            <strong>{EXPRESSION_MODE_LABELS.visual}:</strong> Build conditions visually using a form interface with
            dropdowns and inputs.
          </StackItem>
          <StackItem>
            <strong>{EXPRESSION_MODE_LABELS.raw}:</strong> Write conditions directly as template expressions in the
            format <code>{'${variable operator value}'}</code>
          </StackItem>
        </Stack>
      }
    />
  )
}
