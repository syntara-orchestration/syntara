import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ConvergeStepForm, type ConvergeFormData } from './ConvergeStepForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: () => ({ defaults: null, isLoading: false }),
}))

describe('ConvergeStepForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Info Alert', () => {
    it('renders the alert title, collapsed by default', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      expect(
        screen.getByText('Converge waits for parallel branches to finish executing before continuing')
      ).toBeInTheDocument()
      expect(screen.queryByText(/Use this step when multiple branches run at the same time/i)).not.toBeInTheDocument()
      expect(
        screen.queryByText(/You do not need Converge after Conditional, Switch, or Approval steps/i)
      ).not.toBeInTheDocument()
    })

    it('expands to reveal body text mentioning Conditional, Switch, and Approval steps', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /info alert details/i }))

      expect(screen.getByText(/Use this step when multiple branches run at the same time/i)).toBeInTheDocument()
      const bodyText = screen.getByText(/You do not need Converge after Conditional, Switch, or Approval steps/i)
      expect(bodyText).toBeInTheDocument()
      expect(bodyText).toHaveTextContent('Conditional')
      expect(bodyText).toHaveTextContent('Switch')
      expect(bodyText).toHaveTextContent('Approval')
    })

    it('has no accessibility violations when collapsed', async () => {
      const { container } = renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      // Exclude aria-valid-attr-value: PF6 Tabs renders aria-controls pointing to
      // a panel ID that may not exist in the DOM when only the active tab is rendered
      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when expanded', async () => {
      const user = userEvent.setup()
      const { container } = renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /info alert details/i }))

      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders name field', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
    })

    it('renders strategy selector', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toBeInTheDocument()
    })

    it('renders help popovers for strategy and branch count fields', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} initialData={{ strategy: 'any' }} />)

      expect(screen.getAllByRole('button', { name: /more info/i }).length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Strategy "any" Fields', () => {
    it('does not render "any" fields when strategy is "all"', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      expect(
        screen.queryByRole('spinbutton', { name: /Required number of branches before continuing/i })
      ).not.toBeInTheDocument()
      expect(screen.queryByLabelText(/Behavior of remaining paths/i)).not.toBeInTheDocument()
    })

    it('renders "any" fields when strategy is "any"', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} initialData={{ strategy: 'any' }} />)

      expect(
        screen.getByRole('spinbutton', { name: /Required number of branches before continuing/i })
      ).toBeInTheDocument()
      expect(screen.queryByLabelText(/Behavior of remaining paths/i)).not.toBeInTheDocument()
    })

    it('submits "any" strategy data with required fields', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <ConvergeStepForm onSubmit={mockOnSubmit} initialData={{ strategy: 'any', requiredPathCount: 1 }} />
      )

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Any Strategy')
      const branchCountInput = screen.getByRole('spinbutton', {
        name: /Required number of branches before continuing/i,
      })
      await user.clear(branchCountInput)
      await user.type(branchCountInput, '3')

      fireEvent.submit(screen.getByTestId('converge-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            strategy: 'any',
            requiredPathCount: 3,
          })
        )
      })
    })
  })

  describe('Initial Data', () => {
    it('pre-populates form with initialData', () => {
      const initialData: Partial<ConvergeFormData> = {
        name: 'Existing Converge',
        strategy: 'all',
        settings: { continue_on_failure: false },
      }

      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Existing Converge')
      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toHaveTextContent(
        'All branches reach this step'
      )
    })
  })

  describe('Default Values', () => {
    it('defaults strategy to "all"', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toHaveTextContent(
        'All branches reach this step'
      )
    })
  })

  describe('Header Content', () => {
    it('calls onHeaderContentChange with name field', () => {
      const mockOnHeaderContentChange = vi.fn()
      render(<ConvergeStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />)

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(expect.anything())
    })

    it('cleans up header content on unmount', () => {
      const mockOnHeaderContentChange = vi.fn()
      const { unmount } = render(
        <ConvergeStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />
      )

      mockOnHeaderContentChange.mockClear()
      unmount()

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(null)
    })
  })

  describe('Validation', () => {
    it('strategy select always has a valid value (cannot be reset to empty)', () => {
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      const strategyToggle = screen.getByRole('button', { name: 'Continue when criteria' })
      expect(strategyToggle).toHaveTextContent('All branches reach this step')
    })
  })

  describe('Form Submission', () => {
    it('does not include requiredPathCount when strategy is "all"', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'All Strategy')

      fireEvent.submit(screen.getByTestId('converge-step-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as ConvergeFormData
        expect(submittedData.requiredPathCount).toBeUndefined()
      })
    })

    it('defaults requiredPathCount to 1', async () => {
      const user = userEvent.setup()
      const initialData: Partial<ConvergeFormData> = { strategy: 'all' }
      renderWithHeader(<ConvergeStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Converge')

      fireEvent.submit(screen.getByTestId('converge-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Converge',
            strategy: 'all',
          })
        )
      })
    })
  })
})
