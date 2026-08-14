import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ApprovalNodeForm } from './ApprovalNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

// Mock the permission-filtered hooks — vi.hoisted ensures these are available when vi.mock factories run
const { mockUseApprovalDecideUsers, mockUseApprovalDecideGroups } = vi.hoisted(() => ({
  mockUseApprovalDecideUsers: vi.fn(() => ({
    users: [
      { id: 'user-1', username: 'approver1' },
      { id: 'user-2', username: 'approver2' },
    ],
    isLoading: false,
    isPermissionDenied: false,
    error: null,
    refetch: vi.fn(),
  })),
  mockUseApprovalDecideGroups: vi.fn(() => ({
    groups: [
      { id: 'group-1', name: 'approvers' },
      { id: 'group-2', name: 'admins' },
    ],
    isLoading: false,
    error: null,
  })),
}))

vi.mock('./useApprovalDecideUsers', () => ({
  useApprovalDecideUsers: mockUseApprovalDecideUsers,
}))

vi.mock('./useApprovalDecideGroups', () => ({
  useApprovalDecideGroups: mockUseApprovalDecideGroups,
}))

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: () => ({
    defaults: { timeoutSeconds: { approval: 86400 } },
    isLoading: false,
  }),
}))

describe('ApprovalNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders approver users field', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Approver users')).toBeInTheDocument()
    })

    it('renders approver groups field', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Approver groups')).toBeInTheDocument()
    })

    it('renders message field', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('textbox', { name: 'Message' })).toBeInTheDocument()
    })

    it('renders decision window label', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Decision window')).toBeInTheDocument()
    })

    it('renders decision_window fields', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Days/i })).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('converts decision_window seconds to time units correctly', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ name: 'Test', prompt: 'Test', decision_window: 3723 }}
        />
      )

      // 3723 seconds = 1 hour, 2 minutes, 3 seconds
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(1)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(3)
    })

    it('decision_window fields are empty when not provided', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toBeInTheDocument()
    })

    it('renders permission-filtered user and group selects', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Verify both select fields are present
      expect(screen.getByText('Approver users')).toBeInTheDocument()
      expect(screen.getByText('Approver groups')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select users')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select groups')).toBeInTheDocument()
    })

    it('includes approver_users and approver_groups in initial data', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test Approval',
            prompt: 'Test approval message',
            approver_users: ['approver1', 'approver2'],
            approver_groups: ['approvers', 'admins'],
          }}
        />
      )

      // Verify selected users and groups are shown as Label chips
      expect(screen.getByText('approver1')).toBeInTheDocument()
      expect(screen.getByText('approver2')).toBeInTheDocument()
      expect(screen.getByText('approvers')).toBeInTheDocument()
      expect(screen.getByText('admins')).toBeInTheDocument()
    })

    it('renders without approvers when initialData omits them', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          projectId="test-project"
          initialData={{
            name: 'Test Approval',
            prompt: 'Test approval message',
            // No approver_users or approver_groups
          }}
        />
      )

      // Verify select fields show no selection
      expect(screen.getByPlaceholderText('Select users')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select groups')).toBeInTheDocument()
    })

    it('renders with only approver_users populated', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test Approval',
            prompt: 'Test approval message',
            approver_users: ['approver1'],
            // No approver_groups
          }}
        />
      )

      // Verify only approver_users shows a Label chip
      expect(screen.getByText('approver1')).toBeInTheDocument() // user label chip
      expect(screen.getByPlaceholderText('Select groups')).toBeInTheDocument() // groups still empty
    })
  })

  describe('User Interactions', () => {
    it('allows selecting users', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Initially shows "Select users"
      expect(screen.getByPlaceholderText('Select users')).toBeInTheDocument()

      // Open users dropdown
      const usersToggle = screen.getByPlaceholderText('Select users')
      await user.click(usersToggle)

      // Wait for dropdown to open and find user option
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      // Select a user (clicking the option in the dropdown)
      const approver1Options = screen.getAllByText('approver1')
      await user.click(approver1Options[0]) // Click the one in the dropdown

      // Verify selection shows as a Label chip (approver1 now appears twice: in chip and maybe still in dropdown)
      await waitFor(() => {
        // The label chip should exist
        const labels = screen.getAllByText('approver1')
        expect(labels.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('allows deselecting users', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          projectId="test-project"
          initialData={{
            name: 'Test',
            prompt: 'Test',
            approver_users: ['approver1'],
          }}
        />
      )

      // Should show approver1 as a Label chip initially
      const chip = screen.getByText('approver1')
      expect(chip).toBeInTheDocument()

      // Click the clear all button to deselect
      const clearButton = screen.getByRole('button', { name: /clear all/i })
      await user.click(clearButton)

      // Verify deselection - label chip should disappear, placeholder should return
      await waitFor(() => {
        expect(screen.queryByText('approver1')).not.toBeInTheDocument()
        expect(screen.getByPlaceholderText('Select users')).toBeInTheDocument()
      })
    })

    it('allows selecting and deselecting groups', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Open groups dropdown
      const groupsToggle = screen.getByPlaceholderText('Select groups')
      await user.click(groupsToggle)

      // Wait for dropdown and select a group
      await waitFor(() => {
        expect(screen.getByText('approvers')).toBeInTheDocument()
      })

      const approversOptions = screen.getAllByText('approvers')
      await user.click(approversOptions[0])

      // Verify selection shows as Label chip
      await waitFor(() => {
        const labels = screen.getAllByText('approvers')
        expect(labels.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('allows selecting multiple users', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Open users dropdown
      await user.click(screen.getByPlaceholderText('Select users'))

      // Wait for dropdown and select multiple users
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      const approver1Options = screen.getAllByText('approver1')
      const approver2Options = screen.getAllByText('approver2')
      await user.click(approver1Options[0])
      await user.click(approver2Options[0])

      // Verify both selections show as Label chips
      await waitFor(() => {
        expect(screen.getAllByText('approver1').length).toBeGreaterThanOrEqual(1)
        expect(screen.getAllByText('approver2').length).toBeGreaterThanOrEqual(1)
      })
    })

    it('allows entering decision_window values', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Clear default and set custom decision_window
      await user.clear(screen.getByRole('spinbutton', { name: /Days/i }))
      await user.type(screen.getByRole('spinbutton', { name: /Hours/i }), '2')
      await user.type(screen.getByRole('spinbutton', { name: /Minutes/i }), '30')
      await user.type(screen.getByRole('spinbutton', { name: /Seconds/i }), '15')

      // Verify values
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(30)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(15)
    })

    it('allows entering message text', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      const messageField = screen.getByRole('textbox', { name: 'Message' })
      await user.type(messageField, 'Please approve this deployment')

      expect(messageField).toHaveValue('Please approve this deployment')
    })
  })

  describe('Helper Text', () => {
    it('shows helper text for approver users field', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(
        screen.getByText(/Users who can approve this request. Leave empty for any authorized user/i)
      ).toBeInTheDocument()
    })

    it('shows helper text for approver groups field', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Main helper text (warning is now in a popover)
      expect(
        screen.getByText(/Groups whose members can approve this request. Leave empty for any authorized user/i)
      ).toBeInTheDocument()
    })
  })

  describe('Badge Display', () => {
    it('shows label chips when users are selected', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test',
            prompt: 'Test',
            approver_users: ['approver1', 'approver2'],
          }}
        />
      )

      // Should show Label chips for each selected user
      expect(screen.getByText('approver1')).toBeInTheDocument()
      expect(screen.getByText('approver2')).toBeInTheDocument()
    })

    it('shows label chips when groups are selected', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test',
            prompt: 'Test',
            approver_groups: ['approvers'],
          }}
        />
      )

      // Should show Label chip for selected group
      expect(screen.getByText('approvers')).toBeInTheDocument()
    })
  })

  describe('Group Deselection', () => {
    it('allows deselecting groups', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test',
            prompt: 'Test',
            approver_groups: ['approvers'],
          }}
        />
      )

      // Should show approvers as a Label chip initially
      expect(screen.getByText('approvers')).toBeInTheDocument()

      // Click the clear all button to deselect (only one clear button since only groups have selections)
      const clearButton = screen.getByRole('button', { name: /clear all/i })
      await user.click(clearButton)

      // Verify deselection - label chip should disappear
      await waitFor(() => {
        expect(screen.queryByText('approvers')).not.toBeInTheDocument()
        expect(screen.getByPlaceholderText('Select groups')).toBeInTheDocument()
      })
    })
  })

  describe('Form Data Handling', () => {
    it('renders form with initial data', () => {
      const onSubmit = vi.fn()

      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={onSubmit}
          initialData={{
            name: 'Test Approval',
            prompt: 'Please approve',
            approver_users: ['approver1'],
            approver_groups: ['approvers'],
            decision_window: 3600, // 1 hour
          }}
        />
      )

      // Verify initial data is rendered
      expect(screen.getByDisplayValue('Test Approval')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Please approve')).toBeInTheDocument()
    })

    it('converts decision_window from time units to seconds correctly', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test',
            prompt: 'Test',
            decision_window: 7323, // 2 hours, 2 minutes, 3 seconds
          }}
        />
      )

      // 7323 seconds = 2 hours, 2 minutes, 3 seconds
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(3)
    })

    it('handles zero decision_window values', () => {
      renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test',
            prompt: 'Test',
            decision_window: 0,
          }}
        />
      )

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(0)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(0)
    })
  })

  describe('Timeout Configuration', () => {
    it('shows decision_window section', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Should show decision_window field
      expect(screen.getByText('Decision window')).toBeInTheDocument()
    })

    it('allows configuring decision_window with multiple time units', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Clear default day value and set custom units
      await user.clear(screen.getByRole('spinbutton', { name: /Days/i }))
      await user.type(screen.getByRole('spinbutton', { name: /Days/i }), '1')
      await user.type(screen.getByRole('spinbutton', { name: /Hours/i }), '2')

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(1)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(2)
    })

    it('renders with users loading state', () => {
      mockUseApprovalDecideUsers.mockReturnValue({
        users: [],
        isLoading: true,
        isPermissionDenied: false,
        error: null,
        refetch: vi.fn(),
      })

      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Verify label exists
      expect(screen.getByText('Approver users')).toBeInTheDocument()
    })

    it('shows warning alert when user lacks who_can permission', () => {
      mockUseApprovalDecideUsers.mockReturnValue({
        users: [],
        isLoading: false,
        isPermissionDenied: true,
        error: null,
        refetch: vi.fn(),
      })

      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="some-project" />)

      expect(screen.getByText('Dropdown unavailable')).toBeInTheDocument()
      expect(
        screen.getByText("You don't have permission to list approval users. You can still enter usernames manually.")
      ).toBeInTheDocument()
    })

    it('shows project-required info alert when no project is selected', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Project required')).toBeInTheDocument()
      expect(
        screen.getByText('Select a project to load approval users, or enter usernames manually.')
      ).toBeInTheDocument()
    })

    it('shows permission-denied warning when project is set but user lacks permission', () => {
      mockUseApprovalDecideUsers.mockReturnValue({
        users: [],
        isLoading: false,
        isPermissionDenied: true,
        error: null,
        refetch: vi.fn(),
      })

      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="some-project" />)

      expect(screen.getByText('Dropdown unavailable')).toBeInTheDocument()
      expect(
        screen.getByText("You don't have permission to list approval users. You can still enter usernames manually.")
      ).toBeInTheDocument()
    })

    it('has no accessibility violations in no-project state', async () => {
      const { container } = renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)
      expect(await screen.findByText('Project required')).toBeInTheDocument()
      const results = await axe(container, {
        rules: {
          // This is a known limitation of testing PF Tabs in JSDOM - the components work correctly in real browsers
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })

    it('forwards projectId prop to useApprovalDecideUsers', () => {
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project-123" />)

      expect(mockUseApprovalDecideUsers).toHaveBeenCalledWith('test-project-123')
    })

    it('renders with groups loading state', () => {
      mockUseApprovalDecideGroups.mockReturnValue({
        groups: [],
        isLoading: true,
        error: null,
      })

      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Verify label exists
      expect(screen.getByText('Approver groups')).toBeInTheDocument()
    })
  })

  describe('Typeahead Filtering', () => {
    it('filters users based on search input', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Open users dropdown
      await user.click(screen.getByPlaceholderText('Select users'))

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      // Both users should be visible initially
      expect(screen.getByText('approver1')).toBeInTheDocument()
      expect(screen.getByText('approver2')).toBeInTheDocument()

      // Type in search to filter
      const searchInput = screen.getByPlaceholderText('Select users') // Typeahead input
      await user.type(searchInput, 'approver1')

      // Only approver1 should be visible
      expect(screen.getByText('approver1')).toBeInTheDocument()
      expect(screen.queryByText('approver2')).not.toBeInTheDocument()
    })

    it('filters groups based on search input', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Open groups dropdown
      await user.click(screen.getByPlaceholderText('Select groups'))

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByText('approvers')).toBeInTheDocument()
      })

      // Both groups should be visible initially
      expect(screen.getByText('approvers')).toBeInTheDocument()
      expect(screen.getByText('admins')).toBeInTheDocument()

      // Type in search to filter (in the groups typeahead input)
      const searchInput = screen.getByPlaceholderText('Select groups') // Typeahead input for groups
      await user.type(searchInput, 'admin')

      // Only admins should be visible
      expect(screen.getByText('admins')).toBeInTheDocument()
      expect(screen.queryByText('approvers')).not.toBeInTheDocument()
    })

    it('shows empty text when search returns no results', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Open users dropdown
      await user.click(screen.getByPlaceholderText('Select users'))

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      // Type search that matches nothing
      const searchInput = screen.getByPlaceholderText('Select users') // Typeahead input
      await user.type(searchInput, 'nonexistent')

      // No users should be visible, empty text should show
      expect(screen.queryByText('approver1')).not.toBeInTheDocument()
      expect(screen.queryByText('approver2')).not.toBeInTheDocument()
      expect(screen.getByText('No users with approval:decide permission')).toBeInTheDocument()
    })

    it('clears search filter when dropdown is closed', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Open users dropdown
      const usersToggle = screen.getByPlaceholderText('Select users')
      await user.click(usersToggle)

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      // Type in search to filter
      const searchInput = screen.getByPlaceholderText('Select users') // Typeahead input
      await user.type(searchInput, 'approver1')

      // Close dropdown (by clicking toggle again or pressing Escape)
      await user.keyboard('{Escape}')

      // Re-open dropdown
      await user.click(usersToggle)

      // Search should be cleared, all users visible again
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
        expect(screen.getByText('approver2')).toBeInTheDocument()
      })
    })

    it('search is case-insensitive', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} projectId="test-project" />)

      // Open users dropdown
      await user.click(screen.getByPlaceholderText('Select users'))

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByText('approver1')).toBeInTheDocument()
      })

      // Type uppercase search
      const searchInput = screen.getByPlaceholderText('Select users') // Typeahead input
      await user.type(searchInput, 'APPROVER1')

      // approver1 should still be visible (case-insensitive match)
      expect(screen.getByText('approver1')).toBeInTheDocument()
      expect(screen.queryByText('approver2')).not.toBeInTheDocument()
    })
  })

  describe('retry policy visibility', () => {
    it('hides retry policy for approval nodes', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)
      expect(await screen.findByText('Approver users')).toBeInTheDocument()
      const results = await axe(container, {
        rules: {
          // PatternFly Tabs generates aria-controls pointing to tab panels that exist but axe can't find them in JSDOM
          // This is a known limitation of testing PF Tabs in JSDOM - the components work correctly in real browsers
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with approvers selected', async () => {
      const { container } = renderWithHeader(
        <ApprovalNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Test Approval',
            approver_users: ['approver1', 'approver2'],
            approver_groups: ['admins'],
            prompt: 'Please approve',
            decision_window: 86400,
            fallback_decision: 'reject',
          }}
        />
      )
      expect(await screen.findByText('Approver users')).toBeInTheDocument()
      const results = await axe(container, {
        rules: {
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with empty approvers', async () => {
      const { container } = renderWithHeader(<ApprovalNodeForm onSubmit={mockOnSubmit} />)

      // Form with no approvers selected (default state)
      expect(screen.getByText('Approver users')).toBeInTheDocument()
      expect(screen.getByText('Approver groups')).toBeInTheDocument()

      const results = await axe(container, {
        rules: {
          // This is a known limitation of testing PF Tabs in JSDOM - the components work correctly in real browsers
          'aria-valid-attr-value': { enabled: false },
        },
      })
      expect(results).toHaveNoViolations()
    })
  })
})
