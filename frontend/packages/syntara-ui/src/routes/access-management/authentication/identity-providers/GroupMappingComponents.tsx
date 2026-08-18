import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  ExpandableSection,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  CodeBlock,
  CodeBlockCode,
  Split,
  SplitItem,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import { Tbody, Table } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'
import { Controller, type Control } from 'react-hook-form'

import { FilterBar } from '../../../../components/filters/FilterBar'
import { NxPanelContentStack } from '../../../../components/layout/NxPanelContentStack'
import { NxEmptyStateFilter } from '../../../../components/states/NxEmptyStateFilter'
import { NxEmptyStateNoData } from '../../../../components/states/NxEmptyStateNoData'
import { NxScrollableTableContainer } from '../../../../components/table/NxScrollableTableContainer'
import type { FilterConfig, FilterFieldDefinition } from '../../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../../types/filters'
import { APP_TITLE } from '../../../../utils/appTitle'

import { HintOrError } from './formFieldHelpers'
import type { GroupMappingEditFormValues } from './groupMappingEditFormSchema'
import { EditMappingRow, MappingRow } from './groupMappingFields'
import { GroupMappingTableHead } from './groupMappingTableHead'
import type { GroupMappingEntry, MappedGroup } from './groupMappingUtils'
import { idpHelp } from './idpFieldHelp'
import { IDP_TYPE_PRESETS } from './idpTypePresets'

function entryFieldErrorMessage(
  entryErrors: GroupMappingEditFormValues['entries'] | undefined,
  index: number,
  field: 'idpGroupValue' | 'mappedGroupId'
): string | undefined {
  if (!Array.isArray(entryErrors)) return undefined
  const row = entryErrors[index]
  if (!row || typeof row !== 'object') return undefined
  const fieldError: unknown = row[field]
  if (fieldError && typeof fieldError === 'object' && 'message' in fieldError) {
    const message: unknown = fieldError.message
    return typeof message === 'string' ? message : undefined
  }
  return undefined
}

const GROUP_MAPPING_KEYWORD_FILTER_FIELDS: FilterFieldDefinition[] = [
  {
    key: 'keyword',
    label: 'Keyword',
    type: FilterTypeEnum.TEXT,
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by keyword',
  },
]

/** Module scope: stable reference for inline styles (avoids a new object each render). */
const READ_ONLY_EMPTY_FILTER_STATE_STYLE = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: 0,
} as const

export type EmptyMappingStateProps = {
  /** When undefined, the button is hidden (read-only mode). */
  onTestSignIn?: () => void
  /** When undefined, the button is hidden (read-only mode). */
  onAddManually?: () => void
}

export function EmptyMappingState({ onTestSignIn, onAddManually }: Readonly<EmptyMappingStateProps>) {
  return (
    <EmptyState headingLevel="h2" titleText="No group mappings configured" variant="lg">
      <EmptyStateBody>
        {`Group mappings automatically assign users to ${APP_TITLE} groups based on their identity provider groups.`}
        {(onTestSignIn ?? onAddManually) && ' Discover groups from your IdP, or add mappings manually.'}
      </EmptyStateBody>
      {(onTestSignIn ?? onAddManually) && (
        <EmptyStateFooter>
          <EmptyStateActions>
            {onTestSignIn && (
              <Button variant="primary" onClick={onTestSignIn}>
                Discover groups
              </Button>
            )}
            {onAddManually && (
              <Button variant="secondary" onClick={onAddManually} icon={<RhUiAddIcon />}>
                Add manually
              </Button>
            )}
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}

export type AdvancedSectionProps = {
  control: Control<GroupMappingEditFormValues>
  defaultExpression: string | null
  idpType?: string | null
  rawClaims: string | null
}

export function AdvancedSection({ control, defaultExpression, idpType, rawClaims }: Readonly<AdvancedSectionProps>) {
  return (
    <ExpandableSection toggleText="Advanced" isIndented>
      <Form>
        <Stack hasGutter>
          <StackItem>
            <Controller
              name="expression"
              control={control}
              render={({ field, fieldState }) => (
                <Stack hasGutter>
                  <StackItem>
                    <FormGroup
                      label="Group extraction expression"
                      fieldId="jmespath-expression-tab"
                      labelHelp={idpHelp.groupExtractionExpression}
                    >
                      <TextInput
                        id="jmespath-expression-tab"
                        placeholder="groups[*]"
                        validated={fieldState.error ? 'error' : 'default'}
                        {...field}
                      />
                      <HintOrError
                        error={fieldState.error}
                        hint="JMESPath expression to extract group values from the ID token. Changes are included when you click Save mapping."
                      />
                    </FormGroup>
                  </StackItem>
                  {defaultExpression && field.value !== defaultExpression && (
                    <StackItem>
                      <Button variant="link" onClick={() => field.onChange(defaultExpression)}>
                        Reset to default for {IDP_TYPE_PRESETS[idpType ?? '']?.label ?? 'this provider'}
                      </Button>
                    </StackItem>
                  )}
                </Stack>
              )}
            />
          </StackItem>
          {rawClaims && (
            <StackItem>
              <FormGroup label="Raw token claims" fieldId="raw-claims">
                <CodeBlock>
                  <CodeBlockCode id="raw-claims">{rawClaims}</CodeBlockCode>
                </CodeBlock>
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem>Full token claims from the last group discovery</HelperTextItem>
                  </HelperText>
                </FormHelperText>
              </FormGroup>
            </StackItem>
          )}
        </Stack>
      </Form>
    </ExpandableSection>
  )
}

export type MappingTableRow = {
  rowId: string
  index: number
  /** Read-only list rows include display values */
  idpGroupValue?: string
  mappedGroupId?: string
}

export type MappingTableProps = {
  rows: MappingTableRow[]
  control?: Control<GroupMappingEditFormValues>
  mappedGroups: MappedGroup[]
  isReadOnly?: boolean
  showValidation?: boolean
  entryErrors?: GroupMappingEditFormValues['entries']
  onRemove: (index: number) => void
  onAdd: () => void
  onCreateGroup: (index: number) => void
  /** When false, only the table is rendered (actions row is composed by the parent). Defaults to true in edit mode. */
  showAddMappingAction?: boolean
}

export function MappingTable({
  rows,
  control,
  mappedGroups,
  isReadOnly,
  showValidation,
  entryErrors,
  onRemove,
  onAdd,
  onCreateGroup,
  showAddMappingAction = true,
}: Readonly<MappingTableProps>) {
  /**
   * Align with `MappingRow` action column: `showActionColumn` is true only when `isReadOnly !== true`
   * (this table does not pass `readOnlyAllowRemove`).
   */
  const showActionsColumn = isReadOnly !== true
  const showWildcardHelp = isReadOnly !== true
  const showAddButton = !isReadOnly && showAddMappingAction

  const table = (
    <Table aria-label="Group mappings" variant="compact">
      <GroupMappingTableHead showActionsColumn={showActionsColumn} showWildcardHelp={showWildcardHelp} />
      <Tbody>
        {rows.map((row) => {
          if (isReadOnly) {
            const entry: GroupMappingEntry = {
              key: row.rowId,
              idpGroupValue: row.idpGroupValue ?? '',
              mappedGroupId: row.mappedGroupId ?? '',
            }
            return (
              <MappingRow
                key={row.rowId}
                entry={entry}
                index={row.index}
                mappedGroups={mappedGroups}
                isReadOnly={isReadOnly}
                readOnlyPlainCells={Boolean(isReadOnly)}
                showValidation={showValidation}
                idpErrorMessage={entryFieldErrorMessage(entryErrors, row.index, 'idpGroupValue')}
                groupErrorMessage={entryFieldErrorMessage(entryErrors, row.index, 'mappedGroupId')}
                onRemove={onRemove}
                onCreateGroup={onCreateGroup}
              />
            )
          }

          if (!control) return null

          return (
            <EditMappingRow
              key={row.rowId}
              rowId={row.rowId}
              index={row.index}
              control={control}
              mappedGroups={mappedGroups}
              onRemove={onRemove}
              onCreateGroup={onCreateGroup}
            />
          )
        })}
      </Tbody>
    </Table>
  )

  if (!showAddButton) {
    return table
  }

  return (
    <Stack hasGutter>
      <StackItem>{table}</StackItem>
      <StackItem>
        <Button variant="link" icon={<RhUiAddIcon />} onClick={onAdd}>
          Add mapping
        </Button>
      </StackItem>
    </Stack>
  )
}

export type GroupMappingFormActionsProps = {
  onAdd: () => void
  onReDiscover: () => void
  isListening: boolean
}

/** Add mapping and Re-discover controls below the mapping table (inline edit / dedicated form page). */
export function GroupMappingFormActions({ onAdd, onReDiscover, isListening }: Readonly<GroupMappingFormActionsProps>) {
  return (
    <Split hasGutter>
      <SplitItem>
        <Button variant="link" icon={<RhUiAddIcon />} onClick={onAdd}>
          Add mapping
        </Button>
      </SplitItem>
      <SplitItem>
        <Button
          variant="link"
          onClick={onReDiscover}
          icon={<RhUiSyncIcon />}
          isLoading={isListening}
          isDisabled={isListening}
        >
          {isListening ? 'Waiting for sign-in...' : 'Re-discover groups'}
        </Button>
      </SplitItem>
    </Split>
  )
}

const noopIdpGroupValueChange: (index: number, value: string) => void = () => {
  /* Read-only list view: controls are disabled; handler required by MappingRow */
}
const noopMappedGroupIdChange: (index: number, mappedGroupId: string) => void = () => {
  /* Read-only list view */
}
const noopCreateGroup: (index: number) => void = () => {
  /* Read-only list view */
}
const noopRemoveMapping: (index: number) => void = () => {
  /* Read-only list view: remove action intentionally hidden outside edit mode */
}

type GroupMappingReadOnlyToolbarProps = {
  filters: FilterConfig[]
  onFilterChange: (next: FilterConfig[]) => void
  clearAllFilters: () => void
  /** When undefined, the "Edit group mapping" button is hidden (read-only mode). */
  onEditMapping?: () => void
}

function GroupMappingReadOnlyToolbar({
  filters,
  onFilterChange,
  clearAllFilters,
  onEditMapping,
}: Readonly<GroupMappingReadOnlyToolbarProps>) {
  return (
    <StackItem>
      <FilterBar
        fieldDefinitions={GROUP_MAPPING_KEYWORD_FILTER_FIELDS}
        filters={filters}
        onFilterChange={onFilterChange}
        isCompact
        showClearAll
        clearAllFilters={clearAllFilters}
        toolbarEnd={
          onEditMapping ? (
            <Button variant="primary" icon={<RhUiEditIcon />} onClick={onEditMapping}>
              Edit group mapping
            </Button>
          ) : undefined
        }
      />
    </StackItem>
  )
}

export type ReadOnlyViewProps = {
  entries: GroupMappingEntry[]
  mappedGroups: MappedGroup[]
  /** When undefined, the "Edit group mapping" button is hidden (read-only mode). */
  onEditMapping?: () => void
}

export function ReadOnlyView({ entries, mappedGroups, onEditMapping }: Readonly<ReadOnlyViewProps>) {
  const [filters, setFilters] = useState<FilterConfig[]>([])
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const clearFiltersAndPage = useCallback(() => {
    setFilters([])
    setPage(1)
  }, [])

  const handleFilterChange = useCallback((next: FilterConfig[]) => {
    setFilters(next)
    setPage(1)
  }, [])

  const handlePerPageChange = useCallback((newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }, [])

  const filterTerm = useMemo(() => {
    const keywordFilter = filters.find((f) => f.key === 'keyword')
    if (keywordFilter && typeof keywordFilter.value === 'string') {
      return keywordFilter.value.toLowerCase()
    }
    return ''
  }, [filters])

  const filteredEntries = useMemo(() => {
    if (!filterTerm) return entries
    return entries.filter((e) => {
      const groupName = mappedGroups.find((g) => g.id === e.mappedGroupId)?.name ?? ''
      return e.idpGroupValue.toLowerCase().includes(filterTerm) || groupName.toLowerCase().includes(filterTerm)
    })
  }, [entries, filterTerm, mappedGroups])

  const paginatedEntries = useMemo(() => {
    const start = (page - 1) * perPage
    return filteredEntries.slice(start, start + perPage)
  }, [filteredEntries, page, perPage])

  /** Defensive: parent normally switches to empty state before rendering read-only with zero rows */
  if (entries.length === 0) {
    return (
      <NxEmptyStateNoData
        title="No group mappings"
        description="There are no group mappings to display for this identity provider."
      />
    )
  }

  return (
    <NxPanelContentStack hasGutter>
      <GroupMappingReadOnlyToolbar
        filters={filters}
        onFilterChange={handleFilterChange}
        clearAllFilters={clearFiltersAndPage}
        onEditMapping={onEditMapping}
      />
      {filteredEntries.length === 0 ? (
        <StackItem isFilled style={READ_ONLY_EMPTY_FILTER_STATE_STYLE}>
          <NxEmptyStateFilter clearAllFilters={clearFiltersAndPage} />
        </StackItem>
      ) : (
        <NxScrollableTableContainer
          caption="Group mappings"
          footer={{
            page,
            perPage,
            total: filteredEntries.length,
            hasNext: page * perPage < filteredEntries.length,
            onPrev: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => p + 1),
            onPerPageChange: handlePerPageChange,
          }}
        >
          <GroupMappingTableHead showActionsColumn={false} showWildcardHelp={false} />
          <Tbody>
            {paginatedEntries.map((entry, index) => (
              <MappingRow
                key={entry.key}
                entry={entry}
                index={index}
                mappedGroups={mappedGroups}
                isReadOnly
                readOnlyPlainCells
                showValidation={false}
                onIdpGroupValueChange={noopIdpGroupValueChange}
                onMappedGroupIdChange={noopMappedGroupIdChange}
                onRemove={noopRemoveMapping}
                onCreateGroup={noopCreateGroup}
              />
            ))}
          </Tbody>
        </NxScrollableTableContainer>
      )}
    </NxPanelContentStack>
  )
}
