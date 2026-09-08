import type { MouseEvent, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { ProjectRead } from '../routes/access/types'
import { useProjectStore } from '../stores/useProjectStore'

import { projectSelectorUx } from './projectSelectorUtils'
import { usePaginatedProjects } from './usePaginatedProjects'
import {
  ALL_PROJECTS_VALUE,
  CREATE_PROJECT_VALUE,
  NON_PROJECT_VALUES,
  VIEW_MORE_VALUE,
} from './useProjectSelector.constants'
import { ProjectSelectorDropdown } from './useProjectSelector.dropdown'

/**
 * Module-level flag: true after ANY `useProjectSelector` instance handles an
 * explicit user project selection in the current browser session.  Shared across
 * all mounted instances so the stale-selection guard in one instance (e.g. an
 * always-mounted dialog) cannot clear a selection made by another instance (e.g.
 * the page-level selector).  Resets to false on page reload, which is exactly
 * when the guard *should* validate the persisted ID.
 */
let userExplicitlySelected = false

/** @internal Test-only: reset the module-level explicit-selection flag between test cases. */
export function resetExplicitSelectionFlag(): void {
  userExplicitlySelected = false
}

function resolveMenuToggleStatus(
  requireProject: boolean,
  hasValidationError: boolean,
  selectedProjectId: string | null
): 'danger' | undefined {
  if (requireProject && hasValidationError && !selectedProjectId) return 'danger'
  return undefined
}

function resolveToggleLabel(selectedProjectName: string | undefined, requireProject: boolean): string {
  if (selectedProjectName) return selectedProjectName
  return requireProject ? projectSelectorUx.selectProjectPlaceholder : projectSelectorUx.allProjectsOptionLabel
}

/**
 * Returns the name to show in the toggle, using `storedName` as a fallback when
 * the selected project is temporarily absent from the typeahead results (e.g. a
 * no-match filter was dismissed before the unfiltered list re-fetched).
 * Returns `undefined` when no project is selected so `resolveToggleLabel` shows
 * the placeholder text.
 */
function resolveDisplayName(
  selectedName: string | undefined,
  projectId: string | null,
  storedName: string | null
): string | undefined {
  return selectedName ?? (projectId ? (storedName ?? undefined) : undefined)
}

/**
 * Handles the favorite-star action on a project row. Extracted to module scope to keep
 * `useProjectSelector` under the cyclomatic-complexity limit.
 */
function onFavoriteAction(
  toggleFn: (id: string) => void,
  event: MouseEvent | undefined,
  itemId: string | number | undefined,
  actionId?: string | number
): void {
  if (actionId !== 'fav' || typeof itemId !== 'string' || NON_PROJECT_VALUES.has(itemId)) return
  event?.stopPropagation()
  toggleFn(itemId)
}

type UseProjectSelectorOptions = {
  /** When true, hides the "All projects" option and shows "Select a project" as placeholder. */
  requireProject?: boolean
  /** Server-provided project ID to seed into the store on mount. User selections take precedence afterward. */
  initialProjectId?: string | null
  /**
   * When true with `requireProject` and no project selected in the store, applies `MenuToggle`
   * danger styling so the selector surfaces a validation failure (e.g. save attempted without project).
   */
  hasValidationError?: boolean
  /**
   * Called when the user explicitly selects a project from the dropdown. Use this to clear
   * any validation error state set by the caller (e.g. reset `saveAttemptedWithoutProject`).
   */
  onProjectSelect?: (project: ProjectRead | null) => void
  /** When true, the selector is disabled (greyed out, not interactive). Use for edit mode where project_id is immutable. */
  isDisabled?: boolean
  /** When true, clears the persisted project selection on first mount. Use for pages that must always start with no project (e.g., new workflow builder). */
  clearSelectionOnMount?: boolean
}

type UseProjectSelectorResult = {
  selectedProject: ProjectRead | null
  /**
   * The raw Zustand-persisted project ID. Unlike `selectedProject`, this never
   * becomes null just because the project is absent from the current typeahead
   * filter results. Consumers that gate API queries on the selected project should
   * use this as a stable fallback (e.g. `selectedProject?.id ?? selectedProjectId`).
   */
  selectedProjectId: string | null
  /**
   * A stable `project_id` for API queries: `selectedProject?.id` when the project
   * is visible in the list, falling back to the raw Zustand store ID when the user
   * is typing a filter (so the project temporarily disappears from the list).
   * `undefined` when "All projects" is selected or no project is selected.
   */
  stableProjectId: string | undefined
  isAllProjects: boolean
  projects: ProjectRead[]
  ProjectSelector: ReactNode
  /** Refetch the projects list (e.g., after creating, editing, or deleting a project) */
  refetchProjects: () => Promise<unknown>
}

/**
 * Hook that provides a project selector dropdown and the currently selected project.
 * Uses server-side filtering with debounced typeahead and progressive "View more" loading.
 * When "All projects" is selected, selectedProject is null and no project_id filter is applied.
 * Selection persists across page navigation via Zustand store with localStorage.
 *
 * When `requireProject` is true, the "All projects" option is hidden and the toggle shows
 * `projectSelectorUx.selectProjectPlaceholder` when nothing is selected.
 *
 * When `hasValidationError` is true with `requireProject` and no project selected, the typeahead
 * `MenuToggle` uses `status="danger"`.
 *
 * Includes a "Create project" option in the dropdown that opens a modal dialog.
 *
 * Project rows use PatternFly Select favorites (`isFavorited` + `onActionClick` for `fav`).
 * Favorite IDs persist in `useProjectStore`. Favorites appear in a **Favorites** group (quick access)
 * and again in **Projects** with the full current list (PatternFly favorites pattern).
 */
function favoriteProjectsInResults(projects: ProjectRead[], favoriteProjectIds: readonly string[]): ProjectRead[] {
  const byId = new Map(projects.flatMap((p) => (p.id ? [[p.id, p] as const] : [])))
  return favoriteProjectIds.map((id) => byId.get(id)).filter((p): p is ProjectRead => p !== undefined)
}

type ProjectSelectorSyncEffectsParams = {
  initialProjectId?: string | null
  clearSelectionOnMount?: boolean
  selectedProjectId: string | null
  setSelectedProjectId: (id: string | null, name?: string | null) => void
  isInitialPage: boolean
  projects: ProjectRead[]
  projectsQueryIsFetching: boolean
  selectedProject: ProjectRead | null
  syncName: (name: string | null) => void
}

/** Store sync + stale-selection guard; split out to keep `useProjectSelector` under max-lines. */
/* eslint-disable reactYouMightNotNeedAnEffect/no-event-handler, reactYouMightNotNeedAnEffect/no-pass-data-to-parent -- parameters are Zustand actions / sync helpers, not React child event-handler props */
function useProjectSelectorSyncEffects({
  initialProjectId,
  clearSelectionOnMount,
  selectedProjectId,
  setSelectedProjectId,
  isInitialPage,
  projects,
  projectsQueryIsFetching,
  selectedProject,
  syncName,
}: ProjectSelectorSyncEffectsParams): void {
  const hasClearedOnMount = useRef(false)
  useEffect(() => {
    if (clearSelectionOnMount && !hasClearedOnMount.current) {
      hasClearedOnMount.current = true
      setSelectedProjectId(null)
    }
  }, [clearSelectionOnMount, setSelectedProjectId])

  useEffect(() => {
    if (initialProjectId) setSelectedProjectId(initialProjectId)
  }, [initialProjectId, setSelectedProjectId])

  useEffect(() => {
    if (
      !initialProjectId &&
      selectedProjectId &&
      isInitialPage &&
      !projectsQueryIsFetching &&
      projects.length > 0 &&
      !projects.some((p) => p.id === selectedProjectId) &&
      !userExplicitlySelected
    ) {
      setSelectedProjectId(null)
    }
  }, [initialProjectId, selectedProjectId, projects, setSelectedProjectId, isInitialPage, projectsQueryIsFetching])

  useEffect(() => {
    if (selectedProject?.name) syncName(selectedProject.name)
  }, [selectedProject, syncName])
}
/* eslint-enable reactYouMightNotNeedAnEffect/no-event-handler, reactYouMightNotNeedAnEffect/no-pass-data-to-parent */

export function useProjectSelector(options?: UseProjectSelectorOptions): UseProjectSelectorResult {
  const {
    requireProject = false,
    initialProjectId,
    hasValidationError = false,
    onProjectSelect: onUserProjectSelect,
    isDisabled = false,
    clearSelectionOnMount = false,
  } = options ?? {}
  const {
    selectedProjectId,
    setSelectedProjectId,
    favoriteProjectIds,
    toggleFavoriteProjectId,
    selectedProjectName: storedProjectName,
    setSelectedProjectName: syncName,
  } = useProjectStore()
  const menuToggleStatus = resolveMenuToggleStatus(requireProject, hasValidationError, selectedProjectId)
  const [isOpen, setIsOpen] = useState(false)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [isToggleHovered, setIsToggleHovered] = useState(false)

  const {
    projects,
    filterValue,
    debouncedFilter,
    updateFilter,
    resetPagination,
    clearTypeaheadOnly,
    hasMore,
    isLoadingMore,
    isInitialPage,
    loadMore,
    query: projectsQuery,
  } = usePaginatedProjects()

  const favoriteProjectsOrdered = useMemo(
    () => favoriteProjectsInResults(projects, favoriteProjectIds),
    [projects, favoriteProjectIds]
  )

  const selectedProject = useMemo(
    () => (selectedProjectId ? (projects.find((p) => p.id === selectedProjectId) ?? null) : null),
    [selectedProjectId, projects]
  )

  useProjectSelectorSyncEffects({
    initialProjectId,
    clearSelectionOnMount,
    selectedProjectId,
    setSelectedProjectId,
    isInitialPage,
    projects,
    projectsQueryIsFetching: projectsQuery.isFetching,
    selectedProject,
    syncName,
  })

  const name = resolveDisplayName(selectedProject?.name, selectedProjectId, storedProjectName)
  const toggleLabel = resolveToggleLabel(name, requireProject)
  const isFilterFetching = !!debouncedFilter && projectsQuery.isFetching
  const noResults = projects.length === 0 && !!debouncedFilter && !projectsQuery.isPending

  const handleSelect = useCallback(
    (event: MouseEvent | undefined, value: string | number | undefined) => {
      if (value === CREATE_PROJECT_VALUE) {
        setIsOpen(false)
        setCreateDialogOpen(true)
        return
      }
      if (value === VIEW_MORE_VALUE) {
        event?.preventDefault()
        event?.stopPropagation()
        return
      }
      const projectId = typeof value === 'string' ? value : null
      if (projectId === ALL_PROJECTS_VALUE) {
        userExplicitlySelected = false
        setSelectedProjectId(null)
        setIsOpen(false)
        resetPagination()
        return
      }
      userExplicitlySelected = true
      const selected = projectId ? (projects.find((p) => p.id === projectId) ?? null) : null
      setSelectedProjectId(projectId, selected?.name ?? null)
      setIsOpen(false)
      if (debouncedFilter) updateFilter('')
      else clearTypeaheadOnly()
      if (onUserProjectSelect) onUserProjectSelect(selected)
    },
    [
      setSelectedProjectId,
      resetPagination,
      debouncedFilter,
      updateFilter,
      clearTypeaheadOnly,
      onUserProjectSelect,
      projects,
    ]
  )

  const favoriteProjectIdSet = useMemo(() => new Set(favoriteProjectIds), [favoriteProjectIds])

  const handleFavoriteAction = useCallback(
    (event: MouseEvent | undefined, itemId: string | number | undefined, actionId?: string | number) =>
      onFavoriteAction(toggleFavoriteProjectId, event, itemId, actionId),
    [toggleFavoriteProjectId]
  )

  const ProjectSelector = (
    <ProjectSelectorDropdown
      isDisabled={isDisabled}
      isOpen={isOpen}
      setIsOpen={setIsOpen}
      createDialogOpen={createDialogOpen}
      setCreateDialogOpen={setCreateDialogOpen}
      isToggleHovered={isToggleHovered}
      setIsToggleHovered={setIsToggleHovered}
      clearTypeaheadOnly={clearTypeaheadOnly}
      handleSelect={handleSelect}
      handleFavoriteAction={handleFavoriteAction}
      selectedProjectId={selectedProjectId}
      requireProject={requireProject}
      selectedProject={selectedProject}
      toggleLabel={toggleLabel}
      filterValue={filterValue}
      updateFilter={updateFilter}
      menuToggleStatus={menuToggleStatus}
      isFilterFetching={isFilterFetching}
      noResults={noResults}
      debouncedFilter={debouncedFilter}
      projects={projects}
      favoriteProjectsOrdered={favoriteProjectsOrdered}
      favoriteProjectIdSet={favoriteProjectIdSet}
      hasMore={hasMore}
      isLoadingMore={isLoadingMore}
      loadMore={loadMore}
      projectsQueryRefetch={projectsQuery.refetch}
      setSelectedProjectId={setSelectedProjectId}
    />
  )

  const isAllProjects = selectedProjectId === null
  const stableProjectId = selectedProject?.id ?? (isAllProjects ? undefined : (selectedProjectId ?? undefined))

  return {
    selectedProject,
    selectedProjectId,
    stableProjectId,
    isAllProjects,
    projects,
    ProjectSelector,
    refetchProjects: projectsQuery.refetch,
  }
}
