import { List, ListItem, Stack, StackItem } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'

/**
 * Popover help icon explaining the loop type parameter.
 *
 * Used in Loop step forms.
 */
export function LoopTypeHelp() {
  return (
    <FieldHelpPopover
      headerContent="Type"
      helpText={
        <Stack hasGutter>
          <StackItem>Determine how the workflow should repeat the tasks contained within this step.</StackItem>
          <StackItem>
            <strong>Options:</strong>
          </StackItem>
          <StackItem>
            <List>
              <ListItem>
                <strong>For each:</strong> Best for processing lists. The loop will iterate once for every item in a
                collection (e.g., every "user" in a list of customers).
              </ListItem>
              <ListItem>
                <strong>While:</strong> Best for repetitive checks. The loop will continue to run as long as a specific
                condition remains true (ex: "repeat while the server is busy").
              </ListItem>
            </List>
          </StackItem>
          <StackItem>
            <strong>Static vs. dynamic:</strong> Use for each when you have a fixed set of data from a previous step.
            Use while when you are waiting for an external change or a specific state to be reached.
          </StackItem>
        </Stack>
      }
    />
  )
}
