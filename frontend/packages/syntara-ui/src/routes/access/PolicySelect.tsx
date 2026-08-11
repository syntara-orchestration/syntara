import { type Ref, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { LONG_SELECT_MAX_MENU_HEIGHT, longSelectMenuPopperProps } from '../../components/longSelectMenu'
import longSelectMenuStyles from '../../components/longSelectMenu.module.css'
import { NxSelect } from '../../components/NxSelect'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { fetchAllPoliciesForSelect } from './fetchAllPoliciesForSelect'
import { filterPoliciesForRoleSelect, SELECT_ALL_VALUE } from './policySelectConstants'
import { PolicySelectOptionsList } from './PolicySelectOptionsList'
import { PolicySelectToggle } from './PolicySelectToggle'
import { usePolicySelectAll } from './usePolicySelectAll'

type PolicySelectProps = {
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
  /** Filter policies by project scope. Omit or pass `null`/`undefined` for system (unfiltered), UUID for project-scoped. */
  scopeProjectId?: string | null
  /** When true, fetch only policies whose actions are valid for project-scoped roles. */
  projectEligible?: boolean
  /** When true, the select is disabled (e.g. waiting for project selection). */
  isDisabled?: boolean
}

const DEBOUNCE_MS = 300
const PAGE_SIZE = 50

export function PolicySelect({
  selected,
  onChange,
  hasError,
  scopeProjectId,
  projectEligible,
  isDisabled,
}: Readonly<PolicySelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const [debouncedFilter, setDebouncedFilter] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const { showError } = useAlerts()

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setDebouncedFilter(filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue])

  const policiesQuery = accessClient.useQuery(
    'get',
    '/policies',
    {
      params: {
        query: {
          sort: 'name',
          limit: PAGE_SIZE,
          'name[contains]': debouncedFilter || undefined,
          ...(scopeProjectId ? { project_id: scopeProjectId } : {}),
          ...(projectEligible ? { project_eligible: true } : {}),
        },
      },
    },
    { enabled: isOpen }
  )

  const scopedPolicies = useMemo(
    () => filterPoliciesForRoleSelect(policiesQuery.data?.resources ?? [], { scopeProjectId, projectEligible }),
    [policiesQuery.data?.resources, scopeProjectId, projectEligible]
  )

  const policyOptions = useMemo(() => {
    const fetchedNames = new Set(scopedPolicies.map((p) => p.name))
    const selectedOnly = selected.filter((name) => !fetchedNames.has(name))
    return [
      ...scopedPolicies.map((p) => ({ name: p.name, description: p.description ?? null })),
      ...selectedOnly.map((name) => ({ name, description: null })),
    ]
  }, [scopedPolicies, selected])

  const filteredOptions = useMemo(() => {
    if (filterValue && filterValue !== debouncedFilter) {
      const term = filterValue.toLowerCase()
      return policyOptions.filter((p) => p.name.toLowerCase().includes(term))
    }
    return policyOptions
  }, [policyOptions, filterValue, debouncedFilter])

  const fetchAllMatchingPolicies = useCallback(
    () =>
      fetchAllPoliciesForSelect({
        scopeProjectId,
        projectEligible,
        nameContains: filterValue || debouncedFilter || undefined,
      }),
    [scopeProjectId, projectEligible, filterValue, debouncedFilter]
  )

  const { isSelectingAll, runSelectAll } = usePolicySelectAll({
    selected,
    onChange,
    fetchPolicies: fetchAllMatchingPolicies,
    showError,
    onAfterSelect: () => {
      setFilterValue('')
      inputRef.current?.focus()
    },
  })

  const onSelect = useCallback(
    (_event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => {
      if (value === SELECT_ALL_VALUE) {
        runSelectAll()
        return
      }

      const policyName = value as string
      if (selected.includes(policyName)) {
        onChange(selected.filter((p) => p !== policyName))
      } else {
        onChange([...selected, policyName])
      }
      setFilterValue('')
      inputRef.current?.focus()
    },
    [selected, onChange, runSelectAll]
  )

  const removePolicy = useCallback(
    (policyName: string) => {
      onChange(selected.filter((p) => p !== policyName))
    },
    [selected, onChange]
  )

  const clearAll = useCallback(() => {
    onChange([])
    setFilterValue('')
  }, [onChange])

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }, [])

  const openDropdown = useCallback(() => {
    if (!isOpen) setIsOpen(true)
  }, [isOpen])

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <PolicySelectToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      onToggle={() => setIsOpen(!isOpen)}
      filterValue={filterValue}
      onFilterChange={(val) => {
        setFilterValue(val)
        openDropdown()
      }}
      onFilterFocus={openDropdown}
      selected={selected}
      onRemovePolicy={removePolicy}
      onClearAll={clearAll}
      inputRef={inputRef}
      isDisabled={isDisabled}
      hasError={hasError}
    />
  )

  return (
    <NxSelect
      id="role-policies"
      aria-label="Policies"
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
      isScrollable
      maxMenuHeight={LONG_SELECT_MAX_MENU_HEIGHT}
      popperProps={longSelectMenuPopperProps}
      className={longSelectMenuStyles.containScroll}
    >
      <PolicySelectOptionsList
        isLoading={isLoading}
        filterValue={filterValue}
        filteredOptions={filteredOptions}
        selected={selected}
        isSelectingAll={isSelectingAll}
      />
    </NxSelect>
  )
}
