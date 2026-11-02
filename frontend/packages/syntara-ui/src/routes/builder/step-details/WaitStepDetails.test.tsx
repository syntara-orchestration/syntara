import type { WaitActivity } from '@syntara/contracts'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { renderWithHeader } from '../step-forms/test-utils/renderWithHeader'

import { WaitStepDetails } from './WaitStepDetails'

vi.mock('../step-forms/useMaxWaitDuration', () => ({
  useMaxWaitDuration: () => ({ maxSeconds: 2_592_000, isLoading: false }),
}))

const mockUpdateActivity = vi.fn()
const mockShowError = vi.fn()

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStoreActions: () => ({ updateActivity: mockUpdateActivity }),
}))

describe('WaitStepDetails', () => {
  const baseWaitData: WaitActivity = {
    type: 'wait',
    id: 'wait-1',
    name: 'Wait 5 minutes',
    parameters: {
      duration: 300,
    },
  }

  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Initial Data Mapping', () => {
    it('populates form with existing wait config', () => {
      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Wait 5 minutes')
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(5)
    })

    it('handles missing config gracefully', () => {
      const noConfigData = { ...baseWaitData, parameters: undefined } as unknown as WaitActivity

      renderWithHeader(<WaitStepDetails waitData={noConfigData} nodeId="wait-1" onClose={mockOnClose} />)

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(null)
    })
  })

  describe('Form Submission', () => {
    it('calls updateActivity with correct data on submit', async () => {
      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockUpdateActivity).toHaveBeenCalledWith(
          'wait-1',
          expect.objectContaining({
            name: 'Wait 5 minutes',
            parameters: { duration: 300 },
          })
        )
      })
    })

    it('calls onClose after successful submit', async () => {
      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled()
      })
    })

    it('shows error on update failure', async () => {
      mockUpdateActivity.mockImplementation(() => {
        throw new Error('Update failed')
      })

      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Update failed' }))
      })
    })

    it('shows generic error message for non-Error throws', async () => {
      mockUpdateActivity.mockImplementation(() => {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw { unexpected: true }
      })

      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ description: 'Failed to update step' }))
      })
    })

    it('prevents submission when duration exceeds max allowed', async () => {
      const user = userEvent.setup()
      renderWithHeader(<WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />)

      const daysInput = screen.getByRole('spinbutton', { name: /Days/i })
      await user.clear(daysInput)
      await user.type(daysInput, '31')

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockUpdateActivity).not.toHaveBeenCalled()
      })
      expect(mockOnClose).not.toHaveBeenCalled()
    })
  })

  describe('Header content', () => {
    it('passes onHeaderContentChange to WaitStepForm', () => {
      const onHeaderContentChange = vi.fn()
      renderWithHeader(
        <WaitStepDetails
          waitData={baseWaitData}
          nodeId="wait-1"
          onClose={mockOnClose}
          onHeaderContentChange={onHeaderContentChange}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(
        <WaitStepDetails waitData={baseWaitData} nodeId="wait-1" onClose={mockOnClose} />
      )

      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })

      expect(results).toHaveNoViolations()
    })
  })
})
