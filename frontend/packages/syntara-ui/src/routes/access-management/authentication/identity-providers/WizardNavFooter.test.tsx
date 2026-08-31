import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { WizardNavFooter } from './WizardNavFooter'

const mockGoToNextStep = vi.fn().mockResolvedValue(undefined)
const mockGoToPrevStep = vi.fn()
const mockGoToStepById = vi.fn()

const mockContext = {
  goToNextStep: mockGoToNextStep,
  goToPrevStep: mockGoToPrevStep,
  goToStepById: mockGoToStepById,
  activeStep: { index: 1 },
  steps: [{}, {}],
}

vi.mock('@patternfly/react-core', async () => {
  const actual = await vi.importActual('@patternfly/react-core')
  return {
    ...actual,
    useWizardContext: () => mockContext,
  }
})

describe('WizardNavFooter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockContext.activeStep = { index: 1 }
    mockGoToNextStep.mockResolvedValue(undefined)
  })

  describe('first step', () => {
    it('renders Next button', () => {
      render(<WizardNavFooter />)

      expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
    })

    it('does not render Back button', () => {
      render(<WizardNavFooter />)

      expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
    })

    it('does not render submit button but shows cancel', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} onCancel={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('validates step 1 fields before advancing', async () => {
      const trigger = vi.fn().mockResolvedValue(true)
      const user = userEvent.setup()
      render(<WizardNavFooter trigger={trigger} />)

      await user.click(screen.getByRole('button', { name: 'Next' }))

      await waitFor(() => expect(trigger).toHaveBeenCalled())
      expect(mockGoToNextStep).toHaveBeenCalled()
    })

    it('does not advance when validation fails', async () => {
      const trigger = vi.fn().mockResolvedValue(false)
      const user = userEvent.setup()
      render(<WizardNavFooter trigger={trigger} />)

      await user.click(screen.getByRole('button', { name: 'Next' }))

      await waitFor(() => {
        expect(trigger).toHaveBeenCalled()
      })
      expect(mockGoToNextStep).not.toHaveBeenCalled()
    })

    it('advances without validation when trigger is not provided', async () => {
      const user = userEvent.setup()
      render(<WizardNavFooter />)

      await user.click(screen.getByRole('button', { name: 'Next' }))

      await waitFor(() => {
        expect(mockGoToNextStep).toHaveBeenCalled()
      })
    })
  })

  describe('single-step wizard', () => {
    beforeEach(() => {
      mockContext.activeStep = { index: 1 }
      mockContext.steps = [{}]
    })

    afterEach(() => {
      mockContext.steps = [{}, {}]
    })

    it('renders submit button without Back', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    })

    it('renders Cancel when provided', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} onCancel={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('does not render Cancel when not provided', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    })

    it('calls onSubmit when save is clicked', async () => {
      const onSubmit = vi.fn()
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      expect(onSubmit).toHaveBeenCalledWith(mockGoToStepById)
    })

    it('handles click when onSubmit is not provided', async () => {
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" />)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      expect(mockGoToStepById).not.toHaveBeenCalled()
    })

    it('shows enabled submit button when not saving', () => {
      render(<WizardNavFooter submitLabel="Save" isSaving={false} onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
    })
  })

  describe('middle step', () => {
    beforeEach(() => {
      mockContext.activeStep = { index: 2 }
      mockContext.steps = [{}, {}, {}]
    })

    afterEach(() => {
      mockContext.steps = [{}, {}]
    })

    it('renders Back and Next buttons', () => {
      render(<WizardNavFooter trigger={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
    })

    it('does not render submit button', () => {
      render(<WizardNavFooter trigger={vi.fn()} submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    })

    it('renders Cancel when onCancel is provided', () => {
      render(<WizardNavFooter trigger={vi.fn()} onCancel={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('does not render Cancel when onCancel is not provided', () => {
      render(<WizardNavFooter trigger={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    })

    it('advances without step 1 validation when clicking Next', async () => {
      const trigger = vi.fn()
      const user = userEvent.setup()
      render(<WizardNavFooter trigger={trigger} />)

      await user.click(screen.getByRole('button', { name: 'Next' }))

      await waitFor(() => {
        expect(mockGoToNextStep).toHaveBeenCalled()
      })
      expect(trigger).not.toHaveBeenCalled()
    })

    it('advances without trigger on middle step', async () => {
      const user = userEvent.setup()
      render(<WizardNavFooter />)

      await user.click(screen.getByRole('button', { name: 'Next' }))

      await waitFor(() => {
        expect(mockGoToNextStep).toHaveBeenCalled()
      })
    })
  })

  describe('last step', () => {
    beforeEach(() => {
      mockContext.activeStep = { index: 2 }
    })

    it('renders submit button with provided label', () => {
      render(<WizardNavFooter submitLabel="Save provider" onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Save provider' })).toBeInTheDocument()
    })

    it('renders Back button', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
    })

    it('renders Cancel button when onCancel is provided', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} onCancel={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('does not render Cancel button when onCancel is not provided', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    })

    it('does not render Next button', () => {
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    })

    it('calls onSubmit with goToStepById when submit is clicked', async () => {
      const onSubmit = vi.fn()
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} />)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      expect(onSubmit).toHaveBeenCalledWith(mockGoToStepById)
    })

    it('calls onCancel when cancel is clicked', async () => {
      const onCancel = vi.fn()
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} onCancel={onCancel} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onCancel).toHaveBeenCalled()
    })

    it('disables submit button while saving', () => {
      render(<WizardNavFooter submitLabel="Save" isSaving onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled()
    })

    it('enables submit button when not saving', () => {
      render(<WizardNavFooter submitLabel="Save" isSaving={false} onSubmit={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
    })

    it('handles click when onSubmit is not provided', async () => {
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" />)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      expect(mockGoToStepById).not.toHaveBeenCalled()
    })

    it('calls goToPrevStep when Back is clicked', async () => {
      const user = userEvent.setup()
      render(<WizardNavFooter submitLabel="Save" onSubmit={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: 'Back' }))

      expect(mockGoToPrevStep).toHaveBeenCalled()
    })
  })

  describe('re-render stability', () => {
    it('preserves first step layout on re-render with same props', () => {
      const onCancel = vi.fn()
      const { rerender } = render(<WizardNavFooter onCancel={onCancel} />)

      rerender(<WizardNavFooter onCancel={onCancel} />)

      expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
    })

    it('preserves last step layout on re-render with same props', () => {
      mockContext.activeStep = { index: 2 }
      const onSubmit = vi.fn()
      const onCancel = vi.fn()
      const { rerender } = render(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} onCancel={onCancel} />)

      rerender(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} onCancel={onCancel} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('updates layout when wizard step changes from first to last', () => {
      const onSubmit = vi.fn()
      const { rerender } = render(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} />)

      expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()

      mockContext.activeStep = { index: 2 }
      rerender(<WizardNavFooter submitLabel="Save" onSubmit={onSubmit} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    })

    it('updates layout when onCancel is added', () => {
      const { rerender } = render(<WizardNavFooter />)

      expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()

      const onCancel = vi.fn()
      rerender(<WizardNavFooter onCancel={onCancel} />)

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('updates layout when onCancel is removed', () => {
      const onCancel = vi.fn()
      const { rerender } = render(<WizardNavFooter onCancel={onCancel} />)

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()

      rerender(<WizardNavFooter />)

      expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    })

    it('updates saving state on re-render', () => {
      mockContext.activeStep = { index: 2 }
      const onSubmit = vi.fn()
      const { rerender } = render(<WizardNavFooter submitLabel="Save" isSaving={false} onSubmit={onSubmit} />)

      expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()

      rerender(<WizardNavFooter submitLabel="Save" isSaving onSubmit={onSubmit} />)

      expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled()
    })
  })

  it('has no accessibility violations on first step', async () => {
    const { container } = render(<WizardNavFooter />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations on last step', async () => {
    mockContext.activeStep = { index: 2 }
    const { container } = render(<WizardNavFooter submitLabel="Save provider" onSubmit={vi.fn()} onCancel={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
