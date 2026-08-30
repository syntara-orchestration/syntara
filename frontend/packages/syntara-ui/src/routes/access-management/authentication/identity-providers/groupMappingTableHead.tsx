import { Th, Thead, Tr } from '@patternfly/react-table'

import { GroupColumnLabel, IdpGroupValueColumnLabel } from './groupMappingFields'

export function GroupMappingTableHead({ showActionsColumn }: Readonly<{ showActionsColumn: boolean }>) {
  return (
    <Thead>
      <Tr>
        <Th width={45}>
          <IdpGroupValueColumnLabel />
        </Th>
        <Th width={45}>
          <GroupColumnLabel />
        </Th>
        {showActionsColumn && <Th width={10} screenReaderText="Actions" />}
      </Tr>
    </Thead>
  )
}
