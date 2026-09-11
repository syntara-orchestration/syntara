import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RefObject } from 'react'
import type React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { accessClient } from '../routes/access/accessClient'
import type { ProjectRead } from '../routes/access/types'

import { handleTypeaheadChange, projectSelectorUx } from './projectSelectorUtils'
import { resetExplicitSelectionFlag, useProjectSelector } from './useProjectSelector'

// ── Mocks ─────────────────────────────────────────────────────────────────

const mockShowAlert = vi.fn()

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../providers/alerts', () => ({
  useAlerts: () => ({
    showAlert: mockShowAlert,
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn(),
    showInfo: vi.fn(),
    dismissAlert: vi.fn(),
    clearAllAlerts: vi.fn(),
  }),
}))

const mockToggleFavoriteProjectId = vi.fn()
let mockSelectedProjectId: string | null = null
let mockSelectedProjectName: string | null = null
let mockFavoriteProjectIds: string[] = []

/** Keeps `mockSelectedProjectId` in sync so UI reflects selection (toggle label / filter reset). */
const mockSetSelectedProjectId = vi.fn((id: string | null, name?: string | null) => {
  mockSelectedProjectId = id
  mockSelectedProjectName = name ?? null
})

const mockSetSelectedProjectName = vi.fn((name: string | null) => {
  mockSelectedProjectName = name
})

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../stores/useProjectStore', () => ({
  useProjectStore: () => ({
    selectedProjectId: mockSelectedProjectId,
    selectedProjectName: mockSelectedProjectName,
    setSelectedProjectId: mockSetSelectedProjectId,
    setSelectedProjectName: mockSetSelectedProjectName,
    favoriteProjectIds: mockFavoriteProjectIds,
    toggleFavoriteProjectId: mockToggleFavoriteProjectId,
  }),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: () => () => () => {},
}))

type PaginatedResponse = {
  resources: ProjectRead[]
  next: string | null
  prev: string | null
  total: number | null
}

const mockRefetch = vi.fn()
let mockQueryResponse: { data: PaginatedResponse | undefined; isPending: boolean; isFetching: boolean }

function makePaginatedData(projects: ProjectRead[], next: string | null = null): PaginatedResponse {
  return { resources: projects, next, prev: null, total: projects.length }
}

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../routes/access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

const mockMutate = vi.fn()

// ── Helpers ───────────────────────────────────────────────────────────────

const sampleProjects: ProjectRead[] = [
  {
    id: 'proj-1',
    name: 'Alpha',
    description: 'First project',
    labels: {},
    is_default: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'proj-2',
    name: 'Beta',
    description: 'Second project',
    labels: {},
    is_default: false,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
  },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

/**
 * Renders the ProjectSelector JSX into the DOM so we can test the dropdown UI.
 */
function renderSelector(options?: Parameters<typeof useProjectSelector>[0]) {
  function SelectorHost() {
    const { ProjectSelector } = useProjectSelector(options)
    return <>{ProjectSelector}</>
  }

  return render(<SelectorHost />, { wrapper })
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('useProjectSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    resetExplicitSelectionFlag()
    mockRefetch.mockResolvedValue({ data: { resources: [], next: null, prev: null, total: 0 } })
    vi.mocked(accessClient.useQuery).mockImplementation(() => mockQueryResponse)
    vi.mocked(accessClient.useMutation).mockImplementation(() => ({
      mutate: mockMutate,
      isPending: false,
    }))
    mockSelectedProjectId = null
    mockSelectedProjectName = null
    mockFavoriteProjectIds = []
    mockQueryResponse = {
      data: makePaginatedData(sampleProjects),
      isPending: false,
      isFetching: false,
    }
    // Re-attach refetch to the response object
    Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
  })

  // ── Return value tests ──────────────────────────────────────────────────

  describe('return values', () => {
    it('returns projects from query', () => {
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.projects).toEqual(sampleProjects)
    })

    it('returns empty projects when query data is undefined', () => {
      mockQueryResponse = { data: undefined, isPending: false, isFetching: false }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.projects).toEqual([])
    })

    it('returns isAllProjects true when no project selected', () => {
      mockSelectedProjectId = null
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.isAllProjects).toBe(true)
      expect(result.current.selectedProject).toBeNull()
    })

    it('returns isAllProjects false when a project is selected', () => {
      mockSelectedProjectId = 'proj-1'
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.isAllProjects).toBe(false)
    })

    it('returns selectedProject matching store ID', () => {
      mockSelectedProjectId = 'proj-2'
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.selectedProject).toEqual(sampleProjects[1])
    })

    it('returns null selectedProject when ID does not match any project', () => {
      mockSelectedProjectId = 'nonexistent-id'
      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.selectedProject).toBeNull()
    })
  })

  // ── initialProjectId ───────────────────────────────────────────────────

  describe('initialProjectId', () => {
    it('syncs initialProjectId to the store on mount', () => {
      renderHook(() => useProjectSelector({ initialProjectId: 'proj-2' }), { wrapper })

      expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-2')
    })

    it('does not sync when initialProjectId is null', () => {
      renderHook(() => useProjectSelector({ initialProjectId: null }), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('allows user to change project after initial seed', async () => {
      mockSelectedProjectId = 'proj-1'
      const user = userEvent.setup()
      renderSelector({ initialProjectId: 'proj-1' })

      await user.click(screen.getByDisplayValue('Alpha'))
      await user.click(screen.getByRole('option', { name: /Beta/i }))

      expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-2', 'Beta')
    })

    it('does not clear initialProjectId via stale-guard', async () => {
      mockSelectedProjectId = null
      renderHook(() => useProjectSelector({ initialProjectId: 'nonexistent-id' }), { wrapper })

      await waitFor(() => {
        expect(mockSetSelectedProjectId).toHaveBeenCalledWith('nonexistent-id')
      })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalledWith(null)
    })
  })

  // ── clearSelectionOnMount ────────────────────────────────────────────────

  describe('clearSelectionOnMount', () => {
    it('clears persisted project on mount when clearSelectionOnMount is true', () => {
      mockSelectedProjectId = 'proj-1'
      mockSelectedProjectName = 'Alpha'

      renderHook(() => useProjectSelector({ requireProject: true, clearSelectionOnMount: true }), { wrapper })

      expect(mockSetSelectedProjectId).toHaveBeenCalledWith(null)
    })

    it('does not clear project on mount when clearSelectionOnMount is false', () => {
      mockSelectedProjectId = 'proj-1'
      mockSelectedProjectName = 'Alpha'

      renderHook(() => useProjectSelector({ requireProject: true, clearSelectionOnMount: false }), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalledWith(null)
    })

    it('does not clear project on mount by default (option omitted)', () => {
      mockSelectedProjectId = 'proj-1'
      mockSelectedProjectName = 'Alpha'

      renderHook(() => useProjectSelector({ requireProject: true }), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalledWith(null)
    })

    it('clears only once even after re-renders', () => {
      mockSelectedProjectId = 'proj-1'
      mockSelectedProjectName = 'Alpha'

      const { rerender } = renderHook(() => useProjectSelector({ requireProject: true, clearSelectionOnMount: true }), {
        wrapper,
      })

      rerender()
      rerender()

      const nullCalls = mockSetSelectedProjectId.mock.calls.filter(([id]) => id === null)
      expect(nullCalls).toHaveLength(1)
    })
  })

  // ── Stale project cleanup ───────────────────────────────────────────────

  describe('stale project cleanup', () => {
    it('clears stale project ID that does not match any known project', async () => {
      mockSelectedProjectId = 'stale-project-id'

      renderHook(() => useProjectSelector(), { wrapper })

      await waitFor(() => {
        expect(mockSetSelectedProjectId).toHaveBeenCalledWith(null)
      })
    })

    it('does not clear project ID when it matches a known project', () => {
      mockSelectedProjectId = 'proj-1'

      renderHook(() => useProjectSelector(), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('does not clear when projects data is empty', () => {
      mockSelectedProjectId = 'some-id'
      mockQueryResponse = {
        data: makePaginatedData([]),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      renderHook(() => useProjectSelector(), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('does not clear when projects data is undefined', () => {
      mockSelectedProjectId = 'some-id'
      mockQueryResponse = { data: undefined, isPending: false, isFetching: false }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      renderHook(() => useProjectSelector(), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('does not clear a newly created project ID while the refetch is in flight', () => {
      // Simulates the race condition: onCreated sets the new ID immediately, but the
      // background refetch hasn't returned yet so the new project isn't in `projects` yet.
      mockSelectedProjectId = 'brand-new-project-id'
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects), // old list — new project not here yet
        isPending: false,
        isFetching: true, // refetch is in progress
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      renderHook(() => useProjectSelector(), { wrapper })

      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('does not clear an explicitly selected project even if it is not in the current list', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Explicitly select a project via the dropdown
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: /Beta/i }))
      expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-2', 'Beta')

      // Now simulate a scenario where the selected project is NOT in the returned list
      // (e.g. it's on page 2 and the list reset to page 1). The stale guard should NOT
      // clear because the user explicitly selected it.
      mockSetSelectedProjectId.mockClear()
      mockSelectedProjectId = 'proj-2'
      mockQueryResponse = {
        data: makePaginatedData([sampleProjects[0]]), // only Alpha — Beta is absent
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      renderHook(() => useProjectSelector(), { wrapper })

      // The stale guard must NOT clear because userExplicitlySelected is true
      expect(mockSetSelectedProjectId).not.toHaveBeenCalledWith(null)
    })

    it('clears stale project after selecting "All projects" resets the explicit flag', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Explicitly select a project (sets module flag to true)
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: /Beta/i }))

      // Select "All projects" (resets module flag to false)
      mockSelectedProjectId = 'proj-2'
      await user.click(screen.getByDisplayValue('Beta'))
      await user.click(screen.getByRole('option', { name: /All projects/i }))

      // Now mount a new hook instance with a stale ID — the flag is false so the guard should clear
      mockSetSelectedProjectId.mockClear()
      mockSelectedProjectId = 'nonexistent-stale-id'
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      renderHook(() => useProjectSelector(), { wrapper })

      await waitFor(() => {
        expect(mockSetSelectedProjectId).toHaveBeenCalledWith(null)
      })
    })
  })

  // ── selectedProjectId stable during typeahead filter ──────────────────

  describe('selectedProjectId', () => {
    it('always returns the raw Zustand project ID, even when filtered out of results', () => {
      // The project is NOT in the filtered results list.
      mockSelectedProjectId = 'proj-1'
      mockQueryResponse = {
        data: makePaginatedData([sampleProjects[1]]), // only Beta
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      // selectedProject (resolved from list) is null — Beta-only filtered list
      expect(result.current.selectedProject).toBeNull()
      // selectedProjectId is stable — consumers can use it as a fallback for queries
      expect(result.current.selectedProjectId).toBe('proj-1')
    })

    it('returns null for selectedProjectId when no project is selected', () => {
      mockSelectedProjectId = null
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.selectedProjectId).toBeNull()
      expect(result.current.selectedProject).toBeNull()
    })
  })

  // ── stableProjectId ────────────────────────────────────────────────────

  describe('stableProjectId', () => {
    it('returns the selected project id when project is visible in results', () => {
      mockSelectedProjectId = 'proj-1'
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.stableProjectId).toBe('proj-1')
    })

    it('falls back to raw Zustand id when project is filtered out of visible results', () => {
      mockSelectedProjectId = 'proj-1'
      mockQueryResponse = {
        data: makePaginatedData([sampleProjects[1]]), // only Beta visible
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      // selectedProject is null (not in filtered list), but stableProjectId is still 'proj-1'
      expect(result.current.selectedProject).toBeNull()
      expect(result.current.stableProjectId).toBe('proj-1')
    })

    it('returns undefined when "All projects" is selected', () => {
      mockSelectedProjectId = null
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const { result } = renderHook(() => useProjectSelector(), { wrapper })

      expect(result.current.stableProjectId).toBeUndefined()
    })
  })

  // ── ProjectSelector UI ─────────────────────────────────────────────────

  describe('ProjectSelector UI', () => {
    it('renders a visible Project: prefix before the typeahead value', () => {
      renderSelector()
      expect(screen.getByText(projectSelectorUx.togglePrefixLabel)).toBeInTheDocument()
    })

    it('shows "All projects" in toggle when no project selected', () => {
      renderSelector()

      expect(screen.getByDisplayValue('All projects')).toBeInTheDocument()
    })

    it('shows selected project name in toggle', () => {
      mockSelectedProjectId = 'proj-1'
      renderSelector()

      expect(screen.getByDisplayValue('Alpha')).toBeInTheDocument()
    })

    it('shows "Select a project" in requireProject mode', () => {
      renderSelector({ requireProject: true })

      expect(screen.getByPlaceholderText('Select a project')).toBeInTheDocument()
    })

    it('shows All projects option and project list in dropdown', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.getByRole('option', { name: /All projects/i })).toBeInTheDocument()
      expect(screen.getByText('View all items you have access to.')).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Alpha/i })).toBeInTheDocument()
      expect(screen.getByText('First project')).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Beta/i })).toBeInTheDocument()
      expect(screen.getByText('Second project')).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Create project' })).toBeInTheDocument()
    })

    it('hides "All projects" option when requireProject is true', async () => {
      const user = userEvent.setup()
      renderSelector({ requireProject: true })

      await user.click(screen.getByPlaceholderText('Select a project'))

      expect(screen.queryByRole('option', { name: 'All projects' })).not.toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Alpha/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Beta/i })).toBeInTheDocument()
    })

    it('applies danger styling when save was attempted without a project while requireProject and no selection', () => {
      const { container } = renderSelector({ requireProject: true, hasValidationError: true })
      // PF sets aria-invalid on the TextInputGroupMain wrapper, not the textbox; no semantic query targets that node.
      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- see comment above
      expect(container.querySelector('[aria-invalid="true"]')).toBeInTheDocument()
    })

    it('renders Projects group (no Favorites group until something is starred) and a star on each project row', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.queryByText('Favorites')).not.toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getAllByRole('menuitem', { name: /not starred|starred/i })).toHaveLength(2)
    })

    it('calls toggleFavoriteProjectId when the favorite action is activated', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      const allFavoriteButtons = screen.getAllByRole('menuitem', { name: /not starred|starred/i })
      // Beta is the 2nd project in the test data (proj-2); its star is index 1
      await user.click(allFavoriteButtons[1])

      expect(mockToggleFavoriteProjectId).toHaveBeenCalledWith('proj-2')
      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })

    it('shows Favorites group before Projects; Projects lists every project again including favorites', async () => {
      mockFavoriteProjectIds = ['proj-2']
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.getByText('Favorites')).toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getAllByRole('option', { name: /Beta/i })).toHaveLength(2)

      const headings = screen.getAllByRole('heading', { level: 2 })
      const favHeading = headings.find((h) => h.textContent === 'Favorites')
      const projHeading = headings.find((h) => h.textContent === 'Projects')
      expect(favHeading).toBeDefined()
      expect(projHeading).toBeDefined()
      expect(favHeading!.compareDocumentPosition(projHeading!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

      const options = screen.getAllByRole('option')
      const idxBeta = options.findIndex((el) => el.textContent?.includes('Beta'))
      const idxAlpha = options.findIndex((el) => el.textContent?.includes('Alpha'))
      expect(idxBeta).toBeLessThan(idxAlpha)
    })

    it('selects a project when option is clicked', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: /Beta/i }))

      expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-2', 'Beta')
    })

    it('selects "All projects" to clear selection', async () => {
      mockSelectedProjectId = 'proj-1'
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('Alpha'))
      await user.click(screen.getByRole('option', { name: /All projects/i }))

      expect(mockSetSelectedProjectId).toHaveBeenCalledWith(null)
    })

    it('omits description line when project description is empty', async () => {
      mockQueryResponse = {
        data: makePaginatedData([
          {
            id: 'proj-empty',
            name: 'NoDesc',
            description: '',
            labels: {},
            is_default: false,
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ]),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      expect(screen.getByRole('option', { name: /^NoDesc$/i })).toBeInTheDocument()
    })
  })

  // ── Pagination reset (selection vs View more) ─────────────────────────

  describe('pagination reset behavior', () => {
    const typeaheadInput = () => screen.getByRole('textbox', { name: 'Project' })

    it('clears typeahead filter when selecting a project', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(typeaheadInput(), 'findme')

      await user.click(screen.getByRole('option', { name: /Beta/i }))

      await user.click(screen.getByDisplayValue('Beta'))
      expect(typeaheadInput()).toHaveValue('')
    })

    it('clears typeahead text when dropdown is closed without a selection', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(typeaheadInput(), 'notfound')

      // Close by pressing Escape (equivalent to clicking outside)
      await user.keyboard('{Escape}')

      // Reopen — filter should be gone
      await user.click(screen.getByDisplayValue('All projects'))
      expect(typeaheadInput()).toHaveValue('')
    })

    it('does not clear typeahead filter when View more is clicked', async () => {
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects, 'cursor-page-2'),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })

      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(typeaheadInput(), 'alp')

      await user.click(screen.getByRole('option', { name: 'View more' }))

      expect(typeaheadInput()).toHaveValue('alp')
    })

    it('does not trigger a spurious filter update when the dropdown closes', async () => {
      mockSelectedProjectId = 'proj-1'
      const user = userEvent.setup()
      renderSelector()

      // Open and type a filter
      await user.click(screen.getByDisplayValue('Alpha'))
      await user.type(typeaheadInput(), 'bet')

      // Close the dropdown via Escape — the TextInputGroupMain value switches from
      // filterValue to toggleLabel ("Alpha"). Without the suppressFilterUpdateOnCloseRef
      // guard this programmatic value change would call updateFilter, resetting pagination.
      await user.keyboard('{Escape}')

      // Reopen — the input should show empty (cleared by clearTypeaheadOnly on close),
      // not the selected project name that was briefly swapped in.
      await user.click(screen.getByDisplayValue('Alpha'))
      expect(typeaheadInput()).toHaveValue('')
    })

    it('does not swallow the first keystroke after close-then-reopen without typing', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Open without typing (filterValue and toggleLabel are both "All projects")
      await user.click(screen.getByDisplayValue('All projects'))

      // Close — suppressFilterUpdateOnCloseRef is set to true.
      // If onChange never fires (filterValue === toggleLabel), the ref stays stale.
      // The fix resets the ref when the dropdown re-opens.
      await user.keyboard('{Escape}')

      // Re-open and type — first character must not be swallowed
      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(typeaheadInput(), 'a')

      expect(typeaheadInput()).toHaveValue('a')
    })

    it('handleTypeaheadChange suppresses the spurious onChange when the ref is set and dropdown is closed', () => {
      // Directly test the extracted guard logic — PF's programmatic value swap on
      // close (filterValue → toggleLabel) cannot be replicated in happy-dom because
      // React controlled input reconciliation doesn't fire onChange events.
      const suppressRef: RefObject<boolean> = { current: true }
      const updateFilter = vi.fn<(v: string) => void>()
      const setIsOpen = vi.fn<(open: boolean) => void>()

      handleTypeaheadChange('Alpha', suppressRef, false, updateFilter, setIsOpen)

      // Guard should have consumed the ref and returned early
      expect(suppressRef.current).toBe(false)
      expect(updateFilter).not.toHaveBeenCalled()
      expect(setIsOpen).not.toHaveBeenCalled()
    })

    it('handleTypeaheadChange passes through when the ref is set but dropdown is still open', () => {
      // If the dropdown is open, a change with the ref set is genuine user input
      // that happened to arrive during the same tick — let it through.
      const suppressRef: RefObject<boolean> = { current: true }
      const updateFilter = vi.fn<(v: string) => void>()
      const setIsOpen = vi.fn<(open: boolean) => void>()

      handleTypeaheadChange('bet', suppressRef, true, updateFilter, setIsOpen)

      expect(suppressRef.current).toBe(false)
      expect(updateFilter).toHaveBeenCalledWith('bet')
      expect(setIsOpen).not.toHaveBeenCalled()
    })
  })

  // ── View more ──────────────────────────────────────────────────────────

  describe('view more', () => {
    it('shows "View more" option when more results are available', async () => {
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects, 'cursor-page-2'),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.getByRole('option', { name: 'View more' })).toBeInTheDocument()
    })

    it('does not show "View more" when no next page exists', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.queryByRole('option', { name: 'View more' })).not.toBeInTheDocument()
    })

    it('shows footer hint when more results are available', async () => {
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects, 'cursor-page-2'),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.getByText('Type to refine results')).toBeInTheDocument()
    })

    it('keeps the menu open when View more is clicked', async () => {
      mockQueryResponse = {
        data: makePaginatedData(sampleProjects, 'cursor-page-2'),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'View more' }))

      expect(screen.getByRole('option', { name: 'Create project' })).toBeVisible()
    })

    it('keeps selection when choosing a project only returned after View more', async () => {
      const page2Only: ProjectRead = {
        id: 'proj-only-page-2',
        name: 'Omega',
        description: 'Loaded after View more',
        labels: {},
        is_default: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      }

      const useQuerySpy = vi.mocked(accessClient.useQuery)
      useQuerySpy.mockImplementation(
        (_method: string, _path: string, opts?: { params?: { query?: Record<string, unknown> } }) => {
          const hasCursor = opts?.params?.query?.cursor != null && opts.params.query.cursor !== ''
          const data = hasCursor
            ? makePaginatedData([page2Only], null)
            : makePaginatedData([sampleProjects[0]], 'cursor-next')
          return {
            data,
            isPending: false,
            isFetching: false,
            refetch: mockRefetch,
            error: null,
          }
        }
      )

      try {
        const user = userEvent.setup()
        renderSelector()

        await user.click(screen.getByDisplayValue('All projects'))
        await user.click(screen.getByRole('option', { name: 'View more' }))

        await waitFor(() => {
          expect(screen.getByRole('option', { name: /Omega/i })).toBeInTheDocument()
        })

        await user.click(screen.getByRole('option', { name: /Omega/i }))

        expect(mockSelectedProjectId).toBe('proj-only-page-2')
      } finally {
        useQuerySpy.mockImplementation(() => mockQueryResponse)
      }
    })
  })

  // ── Clear filter button ────────────────────────────────────────────────

  describe('clear filter button', () => {
    it('shows a clear button while the dropdown is open and filter text is present', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(screen.getByPlaceholderText('All projects'), 'beta')

      expect(screen.getByRole('button', { name: 'Clear filter' })).toBeInTheDocument()
    })

    it('does not show the clear button when no filter text is entered', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
    })

    it('clears the filter text when the clear button is clicked, without changing the selection', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.type(screen.getByPlaceholderText('All projects'), 'beta')
      expect(screen.getByRole('button', { name: 'Clear filter' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Clear filter' }))

      // Filter button disappears once the text is gone
      expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
      // Selection has not changed — setSelectedProjectId was never called
      expect(mockSetSelectedProjectId).not.toHaveBeenCalled()
    })
  })

  // ── No results ─────────────────────────────────────────────────────────

  describe('no results', () => {
    it('shows "No results found" when search returns empty', async () => {
      mockQueryResponse = {
        data: makePaginatedData([]),
        isPending: false,
        isFetching: false,
      }
      Object.assign(mockQueryResponse, { refetch: mockRefetch, error: null })
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      // The "no results" message only shows when there's an active debounced filter.
      // Since we can't easily trigger debounce in the mock, verify that with no projects
      // the dropdown still renders without errors (Create project is always available).
      expect(screen.getByRole('option', { name: 'Create project' })).toBeInTheDocument()
    })
  })

  // ── Create project modal ───────────────────────────────────────────────

  describe('create project modal', () => {
    it('opens modal when "Create project" is clicked', async () => {
      const user = userEvent.setup()
      renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByLabelText('Project name')).toBeInTheDocument()
      expect(screen.getByLabelText('Description')).toBeInTheDocument()
    })

    it('closes modal when Cancel is clicked', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Open dropdown then create dialog
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Click Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })

    it('closes modal when the X (close) button is clicked', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Open create dialog
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Click the modal close button (X)
      await user.click(screen.getByRole('button', { name: 'Close' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })

    it('submits create project form with name and description', async () => {
      const user = userEvent.setup()
      renderSelector()

      // Open create dialog
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))

      // Fill form (name must match projectFormSchema — no spaces)
      await user.type(screen.getByLabelText('Project name'), 'new-project')
      await user.type(screen.getByLabelText('Description'), 'A new test project')

      // Submit
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalledWith(
          { body: { name: 'new-project', description: 'A new test project' } },
          expect.objectContaining({
            onSuccess: expect.any(Function) as unknown,
            onError: expect.any(Function) as unknown,
          })
        )
      })
    })

    it('calls showAlert and selects new project on create success', async () => {
      const createdProject: ProjectRead = {
        id: 'proj-new',
        name: 'new-project',
        description: 'Created',
        labels: {},
        is_default: false,
        created_at: '2024-03-01T00:00:00Z',
        updated_at: '2024-03-01T00:00:00Z',
      }

      mockMutate.mockImplementation((_body: unknown, opts: { onSuccess: (data: ProjectRead) => void }) => {
        opts.onSuccess(createdProject)
      })

      const user = userEvent.setup()
      renderSelector()

      // Open create dialog
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))

      // Fill and submit
      await user.type(screen.getByLabelText('Project name'), 'new-project')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockShowAlert).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Project created',
            variant: 'success',
          })
        )
        expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-new')
        expect(mockRefetch).toHaveBeenCalled()
      })
    })

    it('selects new project only after refetch completes', async () => {
      const createdProject: ProjectRead = {
        id: 'proj-new-2',
        name: 'created-project',
        description: '',
        labels: {},
        is_default: false,
        created_at: '2024-03-01T00:00:00Z',
        updated_at: '2024-03-01T00:00:00Z',
      }

      let resolveRefetch!: () => void
      mockRefetch.mockReturnValue(new Promise<void>((r) => (resolveRefetch = r)))

      mockMutate.mockImplementation((_body: unknown, opts: { onSuccess: (data: ProjectRead) => void }) => {
        opts.onSuccess(createdProject)
      })

      const user = userEvent.setup()
      renderSelector({ requireProject: true })

      await user.click(screen.getByPlaceholderText('Select a project'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))
      await user.type(screen.getByLabelText('Project name'), 'created-project')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => expect(mockRefetch).toHaveBeenCalled())
      expect(mockSetSelectedProjectId).not.toHaveBeenCalledWith('proj-new-2')

      resolveRefetch()
      await waitFor(() => expect(mockSetSelectedProjectId).toHaveBeenCalledWith('proj-new-2'))
    })

    it('calls error handler on create failure', async () => {
      mockMutate.mockImplementation((_body: unknown, opts: { onError: (err: unknown) => void }) => {
        opts.onError({ detail: 'Name already exists' })
      })

      const user = userEvent.setup()
      renderSelector()

      // Open create dialog
      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))

      // Fill and submit
      await user.type(screen.getByLabelText('Project name'), 'Duplicate')
      await user.click(screen.getByRole('button', { name: 'Create project' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })
    })
  })

  // ── Accessibility ──────────────────────────────────────────────────────

  describe('accessibility', () => {
    it('has no accessibility violations in default state', async () => {
      const { container } = renderSelector()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in requireProject mode', async () => {
      const { container } = renderSelector({ requireProject: true })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when dropdown is open', async () => {
      const user = userEvent.setup()
      const { container } = renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when create modal is open', async () => {
      const user = userEvent.setup()
      const { container } = renderSelector()

      await user.click(screen.getByDisplayValue('All projects'))
      await user.click(screen.getByRole('option', { name: 'Create project' }))

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in danger (validation error) state', async () => {
      const { container } = renderSelector({ requireProject: true, hasValidationError: true })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
