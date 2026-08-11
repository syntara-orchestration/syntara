import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { fetchAllPoliciesForSelect } from './fetchAllPoliciesForSelect'
import { PolicySelect } from './PolicySelect'
import { SELECT_ALL_LOAD_ERROR } from './policySelectConstants'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
  },
}))

vi.mock('./fetchAllPoliciesForSelect', () => ({
  fetchAllPoliciesForSelect: vi.fn(),
}))

const mockShowError = vi.fn()

vi.mock('../../providers/alerts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../providers/alerts')>()
  return {
    ...actual,
    useAlerts: () => ({
      showAlert: vi.fn(),
      showSuccess: vi.fn(),
      showError: mockShowError,
      showWarning: vi.fn(),
      showInfo: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    }),
  }
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockPolicies = [
  { id: 'p1', name: 'workflow-admin', description: 'Manage workflows', is_project_eligible: false },
  { id: 'p2', name: 'project-viewer', description: 'View projects', is_project_eligible: false },
  { id: 'p3', name: 'execution-runner', description: null, is_project_eligible: false },
]

function renderPolicySelect(overrides: Partial<React.ComponentProps<typeof PolicySelect>> = {}) {
  const props = {
    selected: [] as string[],
    onChange: vi.fn(),
    ...overrides,
  }
  const view = render(<PolicySelect {...props} />, { wrapper })
  return { ...view, onChange: props.onChange }
}

/** PF6 typeahead toggle input */
function getInput() {
  return screen.getByRole('textbox', { name: /type to filter/i })
}

describe('PolicySelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: mockPolicies },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(fetchAllPoliciesForSelect).mockResolvedValue(mockPolicies as never)
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in default state', async () => {
      const { container } = renderPolicySelect()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with selected policies', async () => {
      const { container } = renderPolicySelect({ selected: ['workflow-admin'] })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders with placeholder when no policies are selected', () => {
      renderPolicySelect()
      expect(screen.getByPlaceholderText('Select policies...')).toBeInTheDocument()
    })

    it('does not show placeholder when policies are selected', () => {
      renderPolicySelect({ selected: ['workflow-admin'] })
      expect(screen.queryByPlaceholderText('Select policies...')).not.toBeInTheDocument()
    })

    it('renders selected policies as labels', () => {
      renderPolicySelect({ selected: ['workflow-admin', 'project-viewer'] })
      expect(screen.getByText('workflow-admin')).toBeInTheDocument()
      expect(screen.getByText('project-viewer')).toBeInTheDocument()
    })

    it('shows clear all button when policies are selected', () => {
      renderPolicySelect({ selected: ['workflow-admin'] })
      expect(screen.getByRole('button', { name: 'Clear all selected policies' })).toBeInTheDocument()
    })

    it('does not show clear all button when no policies are selected', () => {
      renderPolicySelect()
      expect(screen.queryByRole('button', { name: 'Clear all selected policies' })).not.toBeInTheDocument()
    })
  })

  describe('Dropdown interactions', () => {
    it('opens dropdown and shows policy options when input is clicked', async () => {
      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      // PF6 Select with hasCheckbox renders options as role="menuitem"
      expect(screen.getByRole('menuitem', { name: /workflow-admin/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /project-viewer/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /execution-runner/i })).toBeInTheDocument()
    })

    it('calls onChange to add a policy when an unselected option is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect()

      await user.click(getInput())

      await user.click(screen.getByRole('checkbox', { name: /workflow-admin/i }))

      expect(onChange).toHaveBeenCalledWith(['workflow-admin'])
    })

    it('calls onChange to remove a policy when a selected option is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect({ selected: ['workflow-admin', 'project-viewer'] })

      await user.click(getInput())

      await user.click(screen.getByRole('checkbox', { name: /workflow-admin/i }))

      expect(onChange).toHaveBeenCalledWith(['project-viewer'])
    })
  })

  describe('Clear all', () => {
    it('calls onChange with empty array when clear all is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect({ selected: ['workflow-admin', 'project-viewer'] })

      await user.click(screen.getByRole('button', { name: 'Clear all selected policies' }))

      expect(onChange).toHaveBeenCalledWith([])
    })
  })

  describe('Remove individual policy', () => {
    it('removes a policy when its label close button is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect({ selected: ['workflow-admin', 'project-viewer'] })

      // PF6 Label close buttons have aria-label "Close <label-text>"
      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      await user.click(closeButtons[0])

      expect(onChange).toHaveBeenCalledWith(['project-viewer'])
    })
  })

  describe('Loading state', () => {
    it('shows loading indicator when data is being fetched', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: null,
        isPending: true,
        isError: false,
        error: null,
        isFetching: true,
        isLoading: true,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      expect(screen.getByText(/Loading policies/i)).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('shows no policies available when there are no options', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        isLoading: false,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      expect(screen.getByText('No policies available')).toBeInTheDocument()
    })
  })

  describe('Filtering', () => {
    it('filters options client-side as user types', async () => {
      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())
      await user.type(getInput(), 'workflow')

      // Client-side filter should narrow results
      await waitFor(() => {
        expect(screen.getByRole('menuitem', { name: /workflow-admin/i })).toBeInTheDocument()
        expect(screen.queryByRole('menuitem', { name: /project-viewer/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('Select all', () => {
    it('shows Select All option when policies are available', async () => {
      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      expect(screen.getByRole('option', { name: 'Select all' })).toBeInTheDocument()
    })

    it('fetches all policies when Select All is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      await waitFor(() => {
        expect(fetchAllPoliciesForSelect).toHaveBeenCalledWith({
          scopeProjectId: undefined,
          projectEligible: undefined,
          nameContains: undefined,
        })
      })
      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith(['workflow-admin', 'project-viewer', 'execution-runner'])
      })
    })

    it('includes policies beyond the first page when Select All is clicked', async () => {
      vi.mocked(fetchAllPoliciesForSelect).mockResolvedValue([
        ...mockPolicies,
        { id: 'p4', name: 'extra-policy', description: 'Extra access' },
      ] as never)

      const user = userEvent.setup()
      const { onChange } = renderPolicySelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith(['workflow-admin', 'project-viewer', 'execution-runner', 'extra-policy'])
      })
    })

    it('merges with existing selection when Select All is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect({ selected: ['workflow-admin'] })

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith(['workflow-admin', 'project-viewer', 'execution-runner'])
      })
    })

    it('fetches only matching policies when a filter is active', async () => {
      const user = userEvent.setup()
      const { onChange } = renderPolicySelect()
      vi.mocked(fetchAllPoliciesForSelect).mockResolvedValue([mockPolicies[0]] as never)

      await user.click(getInput())
      await user.type(getInput(), 'workflow')
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      await waitFor(() => {
        expect(fetchAllPoliciesForSelect).toHaveBeenCalledWith({
          scopeProjectId: undefined,
          projectEligible: undefined,
          nameContains: 'workflow',
        })
      })
      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith(['workflow-admin'])
      })
    })

    it('does not show Select All when no policies are available', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        isLoading: false,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      expect(screen.queryByRole('option', { name: 'Select all' })).not.toBeInTheDocument()
    })

    it('does not show project-only policies in the dropdown for global roles', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: [
            ...mockPolicies,
            { id: 'p4', name: 'policy:update:project', description: 'Project policy', is_project_eligible: true },
          ],
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        isLoading: false,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())

      expect(screen.getByRole('menuitem', { name: /workflow-admin/i })).toBeInTheDocument()
      expect(screen.queryByRole('menuitem', { name: /policy:update:project/i })).not.toBeInTheDocument()
    })

    it('disables Select All while policies are being fetched', async () => {
      vi.mocked(fetchAllPoliciesForSelect).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve(mockPolicies as never), 100)
          })
      )

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      expect(screen.getByRole('option', { name: /Selecting all/i })).toBeDisabled()
    })

    it('shows an error alert when Select All fetch fails', async () => {
      vi.mocked(fetchAllPoliciesForSelect).mockRejectedValue(new Error('network'))

      const user = userEvent.setup()
      renderPolicySelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: 'Select all' }))

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(SELECT_ALL_LOAD_ERROR)
      })
    })
  })

  describe('Selected policies always appear', () => {
    it('shows selected policy names even if not in fetched list', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        isLoading: false,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      renderPolicySelect({ selected: ['orphan-policy'] })

      await user.click(getInput())

      // The selected policy should be in the option list even though API returned empty
      expect(screen.getByRole('menuitem', { name: /orphan-policy/i })).toBeInTheDocument()
    })
  })
})
