import { Divider, SelectList, SelectOption, Spinner } from '@patternfly/react-core'

import { SELECT_ALL_LABEL, SELECT_ALL_VALUE } from './policySelectConstants'
import type { PolicySelectOption } from './policySelectShared'

type PolicySelectOptionsListProps = {
  isLoading: boolean
  filterValue: string
  filteredOptions: PolicySelectOption[]
  selected: string[]
  isSelectingAll: boolean
}

export function PolicySelectOptionsList({
  isLoading,
  filterValue,
  filteredOptions,
  selected,
  isSelectingAll,
}: Readonly<PolicySelectOptionsListProps>) {
  return (
    <SelectList>
      {isLoading && (
        <SelectOption isDisabled>
          <Spinner size="sm" /> Loading policies...
        </SelectOption>
      )}
      {!isLoading && filteredOptions.length === 0 && (
        <SelectOption isDisabled>
          {filterValue ? `No policies match "${filterValue}"` : 'No policies available'}
        </SelectOption>
      )}
      {!isLoading && filteredOptions.length > 0 && (
        <>
          <SelectOption value={SELECT_ALL_VALUE} isDisabled={isSelectingAll}>
            {isSelectingAll ? (
              <>
                <Spinner size="sm" /> Selecting all...
              </>
            ) : (
              SELECT_ALL_LABEL
            )}
          </SelectOption>
          <Divider component="li" />
        </>
      )}
      {!isLoading &&
        filteredOptions.map((policy) => (
          <SelectOption
            key={policy.name}
            value={policy.name}
            hasCheckbox
            isSelected={selected.includes(policy.name)}
            description={policy.description ?? undefined}
          >
            {policy.name}
          </SelectOption>
        ))}
    </SelectList>
  )
}
