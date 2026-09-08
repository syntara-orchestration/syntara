import {
  Button,
  Content,
  ContentVariants,
  Divider,
  InputGroupItem,
  MenuFooter,
  MenuToggle,
  SelectGroup,
  SelectList,
  SelectOption,
  Spinner,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiCloseIcon } from '@patternfly/react-icons'
import { useRef } from 'react'
import type { CSSProperties, Dispatch, MouseEvent, ReactNode, SetStateAction } from 'react'

import { SynSelect } from '../components/SynSelect'
import type { ProjectRead } from '../routes/access/types'
import { ProjectFormModal } from '../routes/access-management/ProjectFormModal'
import { detachPromise } from '../utils/detachPromise'

import {
  getProjectTogglePrefixLabelStyle,
  handleTypeaheadChange,
  PROJECT_SELECTOR_LIST_MAX_HEIGHT,
  PROJECT_SELECTOR_WIDTH,
  projectSelectorUx,
} from './projectSelectorUtils'
import { ALL_PROJECTS_VALUE, CREATE_PROJECT_VALUE, VIEW_MORE_VALUE } from './useProjectSelector.constants'

/**
 * Class matches `.pf-v6-c-input-group__text`; a string avoids importing `input-group.mjs` (pulls `.css`, breaks Vitest).
 */
const PROJECT_TOGGLE_PREFIX_TEXT_CLASS = 'pf-v6-c-input-group__text' as const

const descriptionStyle: CSSProperties = {
  display: 'block',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  maxWidth: '100%',
}

function renderProjectOption(p: ProjectRead, reactKeyPrefix: string, favoriteProjectIdSet: Set<string>) {
  const projectId = p.id ?? ''
  const trimmedDescription = p.description?.trim() || undefined
  const description = trimmedDescription ? (
    <Content component={ContentVariants.small} style={descriptionStyle}>
      {trimmedDescription}
    </Content>
  ) : undefined
  return (
    <SelectOption
      key={`${reactKeyPrefix}-${projectId}`}
      value={projectId}
      description={description}
      isFavorited={projectId !== '' && favoriteProjectIdSet.has(projectId)}
    >
      {p.name}
    </SelectOption>
  )
}

type ProjectGroupsArgs = {
  projects: ProjectRead[]
  favoriteProjectsOrdered: ProjectRead[]
  favoriteProjectIdSet: Set<string>
  hasMore: boolean
  isLoadingMore: boolean
  loadMore: () => void
}

function renderProjectGroups({
  projects,
  favoriteProjectsOrdered,
  favoriteProjectIdSet,
  hasMore,
  isLoadingMore,
  loadMore,
}: ProjectGroupsArgs) {
  const hasFavorites = favoriteProjectsOrdered.length > 0
  const hasProjects = projects.length > 0 || hasMore
  return (
    <>
      {hasFavorites && (
        <SelectGroup key="group-favorites" label={projectSelectorUx.favoritesGroupLabel} labelHeadingLevel="h2">
          {favoriteProjectsOrdered.map((p) => renderProjectOption(p, 'fav', favoriteProjectIdSet))}
        </SelectGroup>
      )}
      {hasFavorites && hasProjects && <Divider key="divider-favorites-projects" />}
      {hasProjects && (
        <SelectGroup key="group-projects" label={projectSelectorUx.projectsGroupLabel} labelHeadingLevel="h2">
          {projects.map((p) => renderProjectOption(p, 'proj', favoriteProjectIdSet))}
          {hasMore && (
            <SelectOption
              key={VIEW_MORE_VALUE}
              value={VIEW_MORE_VALUE}
              isLoadButton={!isLoadingMore}
              isLoading={isLoadingMore}
              onClick={loadMore}
            >
              {isLoadingMore ? <Spinner size="lg" /> : 'View more'}
            </SelectOption>
          )}
        </SelectGroup>
      )}
    </>
  )
}

type FilteredContentArgs = ProjectGroupsArgs & {
  noResults: boolean
  debouncedFilter: string
}

function renderFilteredContent({ noResults, debouncedFilter, ...groupArgs }: FilteredContentArgs) {
  if (noResults) {
    return (
      <SelectOption key="no-results" isAriaDisabled value="no-results">
        {`No results found for "${debouncedFilter}"`}
      </SelectOption>
    )
  }
  return renderProjectGroups(groupArgs)
}

function renderInputUtilities(isOpen: boolean, filterValue: string, isFilterFetching: boolean, onClear: () => void) {
  return (
    <TextInputGroupUtilities style={{ visibility: isOpen ? undefined : 'hidden' }}>
      {isFilterFetching && <Spinner size="sm" aria-label="Filtering projects" />}
      <Button
        variant="plain"
        aria-label="Clear filter"
        onClick={onClear}
        style={{ visibility: filterValue ? 'visible' : 'hidden' }}
        tabIndex={filterValue && isOpen ? 0 : -1}
        icon={<RhUiCloseIcon aria-hidden />}
      />
    </TextInputGroupUtilities>
  )
}

export type ProjectSelectorDropdownProps = {
  isDisabled?: boolean
  isOpen: boolean
  setIsOpen: Dispatch<SetStateAction<boolean>>
  createDialogOpen: boolean
  setCreateDialogOpen: Dispatch<SetStateAction<boolean>>
  isToggleHovered: boolean
  setIsToggleHovered: Dispatch<SetStateAction<boolean>>
  clearTypeaheadOnly: () => void
  handleSelect: (event: MouseEvent | undefined, value: string | number | undefined) => void
  handleFavoriteAction: (
    event: MouseEvent | undefined,
    itemId: string | number | undefined,
    actionId?: string | number
  ) => void
  selectedProjectId: string | null
  requireProject: boolean
  selectedProject: ProjectRead | null
  toggleLabel: string
  filterValue: string
  updateFilter: (val: string) => void
  menuToggleStatus: 'danger' | undefined
  isFilterFetching: boolean
  noResults: boolean
  debouncedFilter: string
  projects: ProjectRead[]
  favoriteProjectsOrdered: ProjectRead[]
  favoriteProjectIdSet: Set<string>
  hasMore: boolean
  isLoadingMore: boolean
  loadMore: () => void
  projectsQueryRefetch: () => Promise<unknown>
  setSelectedProjectId: (id: string | null, name?: string | null) => void
}

export function ProjectSelectorDropdown(props: Readonly<ProjectSelectorDropdownProps>): ReactNode {
  const {
    isDisabled,
    isOpen,
    setIsOpen,
    createDialogOpen,
    setCreateDialogOpen,
    isToggleHovered,
    setIsToggleHovered,
    clearTypeaheadOnly,
    handleSelect,
    handleFavoriteAction,
    selectedProjectId,
    requireProject,
    selectedProject,
    toggleLabel,
    filterValue,
    updateFilter,
    menuToggleStatus,
    isFilterFetching,
    noResults,
    debouncedFilter,
    projects,
    favoriteProjectsOrdered,
    favoriteProjectIdSet,
    hasMore,
    isLoadingMore,
    loadMore,
    projectsQueryRefetch,
    setSelectedProjectId,
  } = props

  /**
   * When the dropdown closes, `TextInputGroupMain` value switches from `filterValue`
   * to `toggleLabel` (the selected project name). This programmatic value change can
   * fire `onChange`, which would call `updateFilter` and reset pagination — dropping
   * View-more pages and triggering the stale-selection guard. This ref suppresses that
   * single spurious `onChange` so only genuine user input reaches `updateFilter`.
   */
  const suppressFilterUpdateOnCloseRef = useRef(false)

  return (
    <>
      <SynSelect
        isOpen={isOpen}
        variant="typeahead"
        shouldFocusFirstItemOnOpen={false}
        onOpenChange={(open) => {
          if (!open) suppressFilterUpdateOnCloseRef.current = true
          setIsOpen(open)
          if (!open) clearTypeaheadOnly()
        }}
        popperProps={{ minWidth: PROJECT_SELECTOR_WIDTH, maxWidth: PROJECT_SELECTOR_WIDTH }}
        onSelect={handleSelect}
        onActionClick={handleFavoriteAction}
        selected={selectedProjectId ?? (requireProject ? undefined : ALL_PROJECTS_VALUE)}
        toggle={(toggleRef) => (
          <Tooltip
            content={selectedProject?.name ?? ''}
            trigger="manual"
            isVisible={isToggleHovered && !isOpen && !!selectedProject}
            position="bottom"
          >
            <MenuToggle
              ref={toggleRef}
              variant="typeahead"
              onClick={() => setIsOpen(!isOpen)}
              isExpanded={isOpen}
              isDisabled={isDisabled}
              status={menuToggleStatus}
              style={{ minWidth: PROJECT_SELECTOR_WIDTH }}
              onMouseEnter={() => setIsToggleHovered(true)}
              onMouseLeave={() => setIsToggleHovered(false)}
            >
              <TextInputGroup isPlain isDisabled={isDisabled}>
                <InputGroupItem isPlain isBox={false}>
                  <Content
                    className={PROJECT_TOGGLE_PREFIX_TEXT_CLASS}
                    style={getProjectTogglePrefixLabelStyle(isDisabled)}
                  >
                    {projectSelectorUx.togglePrefixLabel}
                  </Content>
                </InputGroupItem>
                <TextInputGroupMain
                  value={isOpen ? filterValue : toggleLabel}
                  aria-label="Project"
                  aria-invalid={menuToggleStatus === 'danger'}
                  onChange={(_e, val) =>
                    handleTypeaheadChange(val, suppressFilterUpdateOnCloseRef, isOpen, updateFilter, setIsOpen)
                  }
                  onClick={() => {
                    if (!isOpen) {
                      suppressFilterUpdateOnCloseRef.current = false
                      setIsOpen(true)
                    }
                  }}
                  placeholder={toggleLabel}
                  autoComplete="off"
                />
                {renderInputUtilities(isOpen, filterValue, isFilterFetching, () => updateFilter(''))}
              </TextInputGroup>
            </MenuToggle>
          </Tooltip>
        )}
      >
        <SelectList style={{ maxHeight: PROJECT_SELECTOR_LIST_MAX_HEIGHT, overflow: 'auto' }}>
          {!requireProject && (
            <>
              <SelectOption
                key={ALL_PROJECTS_VALUE}
                value={ALL_PROJECTS_VALUE}
                description={projectSelectorUx.allProjectsOptionDescription}
              >
                {projectSelectorUx.allProjectsOptionLabel}
              </SelectOption>
              <Divider key="divider-all" />
            </>
          )}
          {renderFilteredContent({
            noResults,
            debouncedFilter,
            projects,
            favoriteProjectsOrdered,
            favoriteProjectIdSet,
            hasMore,
            isLoadingMore,
            loadMore,
          })}
        </SelectList>
        <Divider key="divider-create" />
        <SelectList>
          <SelectOption key={CREATE_PROJECT_VALUE} value={CREATE_PROJECT_VALUE} icon={<RhUiAddIcon />}>
            Create project
          </SelectOption>
        </SelectList>
        {hasMore && !noResults && !isFilterFetching && (
          <MenuFooter>
            <Content component={ContentVariants.small}>Type to refine results</Content>
          </MenuFooter>
        )}
      </SynSelect>

      <ProjectFormModal
        isOpen={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        onSuccess={() => {}}
        onCreated={(created) => {
          setCreateDialogOpen(false)
          const newId = created.id ?? null
          detachPromise(
            projectsQueryRefetch().finally(() => {
              setSelectedProjectId(newId)
            })
          )
        }}
      />
    </>
  )
}
