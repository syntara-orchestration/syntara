import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { renderWithHeader } from './test-utils/renderWithHeader'
import { WaitStepForm, type WaitFormData } from './WaitStepForm'

vi.mock('./useMaxWaitDuration', () => ({
  useMaxWaitDuration: () => ({ maxSeconds: 2_592_000, isLoading: false }),
}))

describe('WaitStepForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders name field', () => {
      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
    })

    it('renders duration fields', () => {
      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toBeInTheDocument()
    })

    it('renders duration labels', () => {
      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Days')).toBeInTheDocument()
      expect(screen.getByText('Hours')).toBeInTheDocument()
      expect(screen.getByText('Minutes')).toBeInTheDocument()
      expect(screen.getByText('Seconds')).toBeInTheDocument()
    })

    it('renders "Wait duration" label', () => {
      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Wait duration')).toBeInTheDocument()
    })
  })

  describe('Initial Data', () => {
    it('pre-populates form with initialData (1d 2h 30m)', () => {
      // 1 day + 2 hours + 30 minutes = 93000 seconds
      const initialData: Partial<WaitFormData> = {
        name: 'Existing Wait',
        duration: 93000,
      }

      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Existing Wait')
      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(1)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(1)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(50)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(0)
    })

    it('shows empty inputs when no initialData provided', () => {
      renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(null)
    })
  })

  describe('Validation', () => {
    it('does not submit when duration is not set', async () => {
      render(<WaitStepForm onSubmit={mockOnSubmit} initialData={{ name: 'Test Wait' }} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })
    })

    it('does not submit when duration exceeds max', async () => {
      // 31 days = 2678400 seconds > max 2592000
      const initialData: Partial<WaitFormData> = {
        name: 'Too Long',
        duration: 2_678_400,
      }

      render(<WaitStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })
    })
  })

  describe('Form Submission', () => {
    it('submits valid duration data as total seconds', async () => {
      // 1 hour + 30 minutes = 5400 seconds
      const initialData: Partial<WaitFormData> = {
        name: 'My Wait',
        duration: 5400,
      }

      render(<WaitStepForm onSubmit={mockOnSubmit} initialData={initialData} />)

      fireEvent.submit(screen.getByTestId('wait-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const calledWith = mockOnSubmit.mock.calls[0][0] as WaitFormData
        expect(calledWith.name).toBe('My Wait')
        expect(calledWith.duration).toBe(5400)
      })
    })
  })

  describe('Header Content', () => {
    it('calls onHeaderContentChange with name field', () => {
      const mockOnHeaderContentChange = vi.fn()
      render(<WaitStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />)

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(expect.anything())
    })

    it('cleans up header content on unmount', () => {
      const mockOnHeaderContentChange = vi.fn()
      const { unmount } = render(
        <WaitStepForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />
      )

      mockOnHeaderContentChange.mockClear()
      unmount()

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(null)
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(<WaitStepForm onSubmit={mockOnSubmit} />)

      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })

      expect(results).toHaveNoViolations()
    })
  })
})
