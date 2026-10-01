import { Stack, StackItem } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'

import { LOOP_WHILE_CONDITION_HELP } from './stepFieldHelpText'

/**
 * Popover help for the while-loop conditional expression field.
 */
export function WhileConditionHelp() {
  return (
    <FieldHelpPopover
      headerContent="Conditional expression (while loop)"
      helpText={
        <Stack hasGutter>
          <StackItem>{LOOP_WHILE_CONDITION_HELP}</StackItem>
          <StackItem>
            <strong>Visual expression builder:</strong> Build conditions visually using a form interface with dropdowns
            and inputs.
          </StackItem>
          <StackItem>
            <strong>Custom expression:</strong> Write conditions directly as template expressions in the format{' '}
            <code>{'${variable operator value}'}</code>
          </StackItem>
        </Stack>
      }
    />
  )
}
