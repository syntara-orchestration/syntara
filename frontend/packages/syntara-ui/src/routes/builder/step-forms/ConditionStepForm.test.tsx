import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EXPRESSION_MODE_LABELS } from '../../../components/expressions/expressionBuilderLabels'

import { ConditionStepForm, type ConditionFormData } from './ConditionStepForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

describe('ConditionStepForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders name field', () => {
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
    })

    it('renders conditional expression field', () => {
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('group', { name: /Condition/i })).toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('validates required condition field', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'No Condition')
      fireEvent.submit(screen.getByTestId('condition-step-form'))

      // Form should not submit without condition
      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })
    })
  })

  describe('Initial Data', () => {
    it('pre-populates form with initialData', () => {
      const initialData: ConditionFormData = {
        name: 'Existing Condition',
        condition: '${status == "active"}',
      }

      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Existing Condition')
      // Note: Expression builder field value validation would require examining the internal state
    })
  })

  describe('Header Content', () => {
    it('calls onHeaderContentChange with name field', () => {
      const mockOnHeaderContentChange = vi.fn()
      render(<ConditionStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />)

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(expect.anything())
    })

    it('cleans up header content on unmount', () => {
      const mockOnHeaderContentChange = vi.fn()
      const { unmount } = render(
        <ConditionStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />
      )

      mockOnHeaderContentChange.mockClear()
      unmount()

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(null)
    })
  })

  describe('Conditional Expression Help', () => {
    it('renders help icon', () => {
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: /more info/i })).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('submits form with valid condition data', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      const nameInput = screen.getByPlaceholderText(/Enter activity name/i)
      await user.click(nameInput)
      await user.paste('Test Condition')

      // Switch to raw mode and enter expression
      await user.click(screen.getByRole('button', { name: EXPRESSION_MODE_LABELS.visual }))
      await user.click(await screen.findByRole('option', { name: 'Freeform text' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${result > 0}')

      fireEvent.submit(screen.getByTestId('condition-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const callArgs: unknown = mockOnSubmit.mock.calls[0][0]
        expect(callArgs).toMatchObject({
          name: 'Test Condition',
          condition: '${result > 0}',
        })
      })
    }, 10_000)

    it('submits without logicType field (removed from interface)', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ConditionStepForm onSubmit={mockOnSubmit} />)

      const nameInput = screen.getByPlaceholderText(/Enter activity name/i)
      await user.click(nameInput)
      await user.paste('Another Condition')
      await user.click(screen.getByRole('button', { name: EXPRESSION_MODE_LABELS.visual }))
      await user.click(await screen.findByRole('option', { name: 'Freeform text' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${x == 5}')

      fireEvent.submit(screen.getByTestId('condition-step-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as ConditionFormData
        expect(submittedData).not.toHaveProperty('logicType')
        expect(submittedData.name).toBe('Another Condition')
        expect(submittedData.condition).toBe('${x == 5}')
      })
    })
  })
})
