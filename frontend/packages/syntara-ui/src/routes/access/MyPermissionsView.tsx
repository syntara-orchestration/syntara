import { Button, Flex, Tooltip } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ThProps } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'

import type { PermissionEntry } from './types'
import { useAllPermissions } from './useAllPermissions'

function textContainsFilter(key: string, label: string): FilterFieldDefinition {
  return {
    key,
    label,
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: `Filter by ${label.toLowerCase()}`,
  }
}

const FILTER_FIELD_DEFS: FilterFieldDefinition[] = [
  textContainsFilter('policy_name', 'Policy'),
  {
    key: 'effect',
    label: 'Effect',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: 'allow', label: 'Allow' },
      { value: 'deny', label: 'Deny' },
    ],
    placeholder: 'Filter by effect',
  },
  textContainsFilter('actions', 'Action'),
  textContainsFilter('scope', 'Scope'),
  textContainsFilter('project', 'Project'),
]

type SortDirection = 'asc' | 'desc'

const SORT_FIELDS: Record<number, keyof PermissionEntry> = {
  0: 'policy_name',
  1: 'effect',
  3: 'scope',
  4: 'project',
}

function matchesFilter(perm: PermissionEntry, filter: FilterConfig): boolean {
  const val = String(filter.value).toLowerCase()
  switch (filter.key) {
    case 'policy_name':
      return perm.policy_name.toLowerCase().includes(val)
    case 'effect':
      return perm.effect.toLowerCase() === val
    case 'actions':
      return perm.actions.some((a) => a.toLowerCase().includes(val))
    case 'scope':
      return perm.scope.toLowerCase().includes(val)
    case 'project':
      return (perm.project ?? '').toLowerCase().includes(val)
    default:
      return true
  }
}

function comparePermissions(a: PermissionEntry, b: PermissionEntry, field: keyof PermissionEntry): number {
  const aVal = a[field] ?? ''
  const bVal = b[field] ?? ''
  if (Array.isArray(aVal) && Array.isArray(bVal)) {
    return aVal.join(',').localeCompare(bVal.join(','))
  }
  return String(aVal).localeCompare(String(bVal))
}

function PermissionsTableContent({
  permissions,
  getSortParams,
}: Readonly<{
  permissions: PermissionEntry[]
  getSortParams: (columnIndex: number) => ThProps['sort']
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Policy</Th>
          <Th sort={getSortParams(1)}>Effect</Th>
          <Th>Actions</Th>
          <Th sort={getSortParams(3)}>Scope</Th>
          <Th sort={getSortParams(4)}>Project</Th>
        </Tr>
      </Thead>
      <Tbody>
        {permissions.map((perm) => (
          <Tr key={`${perm.policy_name}-${perm.effect}-${perm.actions.join(',')}-${perm.scope}-${perm.project ?? ''}`}>
            <Td dataLabel="Policy">
              <code>{perm.policy_name}</code>
            </Td>
            <Td dataLabel="Effect">
              <SynLabel
                color={perm.effect === 'allow' ? 'green' : 'red'}
                icon={perm.effect === 'allow' ? <RhUiCheckCircleIcon /> : <RhUiCloseCircleIcon />}
              >
                {perm.effect}
              </SynLabel>
            </Td>
            <Td dataLabel="Actions">
              <Flex gap={{ default: 'gapXs' }} flexWrap={{ default: 'wrap' }}>
                {perm.actions.map((a) => (
                  <SynLabel key={a} color="blue">
                    {a}
                  </SynLabel>
                ))}
              </Flex>
            </Td>
            <Td dataLabel="Scope">{perm.scope || '-'}</Td>
            <Td dataLabel="Project">{perm.project || '-'}</Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export function MyPermissionsView() {
  const { permissions, isLoading, error, refetch } = useAllPermissions()

  const [filters, setFilters] = useState<FilterConfig[]>([])
  const [activeSortIndex, setActiveSortIndex] = useState<number | undefined>(undefined)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const hasActiveFilters = filters.length > 0

  const handleFilterChange = useCallback((newFilters: FilterConfig[]) => {
    setFilters(newFilters)
    setPage(1)
  }, [])

  const clearAllFilters = useCallback(() => {
    setFilters([])
    setPage(1)
  }, [])

  const handlePerPageChange = useCallback((newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }, [])

  const getSortParams = useCallback(
    (columnIndex: number): ThProps['sort'] => ({
      sortBy: {
        index: activeSortIndex,
        direction: sortDirection,
        defaultDirection: 'asc',
      },
      onSort: (_event, index, direction) => {
        setActiveSortIndex(index)
        setSortDirection(direction as SortDirection)
        setPage(1)
      },
      columnIndex,
    }),
    [activeSortIndex, sortDirection]
  )

  const filtered = useMemo(() => {
    if (filters.length === 0) return permissions
    return permissions.filter((p) => filters.every((f) => matchesFilter(p, f)))
  }, [permissions, filters])

  const sorted = useMemo(() => {
    if (activeSortIndex === undefined) return filtered
    const field = SORT_FIELDS[activeSortIndex]
    if (!field) return filtered

    const result = [...filtered]
    result.sort((a, b) => {
      const cmp = comparePermissions(a, b, field)
      return sortDirection === 'desc' ? -cmp : cmp
    })
    return result
  }, [filtered, activeSortIndex, sortDirection])

  const totalFiltered = sorted.length
  const startIndex = (page - 1) * perPage
  const pageData = useMemo(() => sorted.slice(startIndex, startIndex + perPage), [sorted, startIndex, perPage])
  const hasNextPage = startIndex + perPage < totalFiltered

  const tableFooter = useMemo(
    () => ({
      page,
      perPage,
      total: totalFiltered,
      hasNext: hasNextPage,
      onPrev: () => setPage((p) => Math.max(1, p - 1)),
      onNext: () => setPage((p) => p + 1),
      onPerPageChange: handlePerPageChange,
    }),
    [page, perPage, totalFiltered, hasNextPage, handlePerPageChange]
  )

  return (
    <SynPanelContentStack hasGutter>
      <NxListPanelView
        isPending={isLoading}
        error={error}
        onRetry={() => detachPromise(refetch())}
        isEmpty={sorted.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={clearAllFilters}
        noDataState={
          <SynEmptyStateNoData title="No permissions" description="The current user has no permissions assigned." />
        }
        toolbar={
          <NxListPanelToolbar
            filters={filters}
            filterDefinitions={FILTER_FIELD_DEFS}
            onFilterChange={handleFilterChange}
            clearAllFilters={clearAllFilters}
            toolbarItemsAfterFilters={
              <Tooltip content="Refresh permissions">
                <Button
                  variant="plain"
                  aria-label="Refresh permissions"
                  onClick={() => detachPromise(refetch())}
                  icon={<RhUiSyncIcon />}
                />
              </Tooltip>
            }
          />
        }
        body={
          <NxListPanelTable caption="User permissions" footer={tableFooter}>
            <PermissionsTableContent permissions={pageData} getSortParams={getSortParams} />
          </NxListPanelTable>
        }
      />
    </SynPanelContentStack>
  )
}
