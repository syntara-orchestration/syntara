import { List, ListItem, Stack, StackItem } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'

/**
 * Popover help icon explaining the continue when criteria parameter.
 *
 * Used in Converge step forms.
 */
export function ContinueWhenCriteriaHelp() {
  return (
    <FieldHelpPopover
      headerContent="Continue when criteria"
      helpText={
        <Stack hasGutter>
          <StackItem>
            Determine when the workflow should continue past this converge step after parallel branches.
          </StackItem>
          <StackItem>
            <List>
              <ListItem>
                <strong>All branches reach this step:</strong> The workflow will wait until every incoming branch has
                completed before continuing.
              </ListItem>
              <ListItem>
                <strong>Any branches reach this step:</strong> The workflow will continue once the specified number of
                incoming branches have completed.
              </ListItem>
            </List>
          </StackItem>
        </Stack>
      }
    />
  )
}
