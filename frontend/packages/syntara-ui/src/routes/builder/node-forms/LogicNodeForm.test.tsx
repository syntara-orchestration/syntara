import { ActivityTypeEnum } from '@syntara/contracts'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LogicFormData } from './LogicNodeForm'
import { LogicNodeForm } from './LogicNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

vi.mock('./useMaxWaitDuration', () => ({
  useMaxWaitDuration: () => ({ maxSeconds: 2_592_000, isLoading: false }),
}))

describe('LogicNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Delegation to specialized forms', () => {
    it('renders ConditionNodeForm when logicType is condition', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONDITION,
            name: 'Test Condition',
            condition: '${x > 0}',
          }}
        />
      )

      // Verify ConditionNodeForm is rendered by checking for its unique elements
      expect(screen.getByRole('group', { name: /Expression builder/i })).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Test Condition')
    })

    it('renders LoopNodeForm when logicType is loop', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.LOOP,
            name: 'Test Loop',
            type: 'forEach',
            items: '${items}',
          }}
        />
      )

      // Verify LoopNodeForm is rendered by checking for its unique elements
      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Test Loop')
      expect(screen.getByRole('button', { name: 'Type' })).toBeInTheDocument()
    })

    it('renders ConvergeNodeForm when logicType is converge', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONVERGE,
            name: 'Test Converge',
            strategy: 'all',
          }}
        />
      )

      // Verify ConvergeNodeForm is rendered by checking for its unique elements
      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Test Converge')
      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toBeInTheDocument()
    })

    it('renders SwitchNodeForm when logicType is switch', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.SWITCH,
            name: 'Test Switch',
            cases: [
              {
                caseId: 'c1',
                label: 'Path 1',
                condition: '${status} == "active"',
              },
            ],
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Test Switch')
      expect(screen.getByDisplayValue('Path 1')).toBeInTheDocument()
    })

    it('renders SwitchNodeForm and submits with logicType', async () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.SWITCH,
            name: 'Switch Submit',
            cases: [{ caseId: 'c1', label: 'Path 1', condition: '${x} == 1' }],
          }}
        />
      )

      fireEvent.submit(screen.getByTestId('switch-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const submittedData = mockOnSubmit.mock.calls[0][0] as LogicFormData
        expect(submittedData.logicType).toBe(ActivityTypeEnum.SWITCH)
        expect(submittedData.name).toBe('Switch Submit')
      })
    })

    it('renders WaitNodeForm when logicType is wait', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.WAIT,
            name: 'Test Wait',
            duration: 95415,
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Test Wait')
      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(1)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(30)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(15)
    })

    it('returns null when logicType is unknown', () => {
      const { container } = render(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: 'unknown',
          }}
        />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('returns null when logicType is undefined', () => {
      const { container } = render(<LogicNodeForm onSubmit={mockOnSubmit} />)

      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('Data mapping and submission', () => {
    it('maps condition data correctly and adds logicType on submit', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONDITION,
            name: 'Initial Name',
            condition: '${initial}',
          }}
        />
      )

      const nameInput = screen.getByPlaceholderText(/Enter activity name/i)
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Condition')

      await user.click(screen.getByRole('button', { name: /Expression editor mode/i }))
      await user.click(await screen.findByRole('option', { name: 'Custom expression' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.clear(rawInput)
      await user.paste('${x > 5}')

      fireEvent.submit(screen.getByTestId('condition-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith({
          name: 'Updated Condition',
          condition: '${x > 5}',
          logicType: ActivityTypeEnum.CONDITION,
        })
      })
    })

    it('maps loop data correctly and adds logicType on submit', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.LOOP,
            name: 'Test Loop',
            type: 'forEach',
            items: '${items}',
            maxIterations: 10,
            indexVariable: 'i',
            itemVariable: 'item',
          }}
        />
      )

      const nameInput = screen.getByPlaceholderText(/Enter activity name/i)
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Loop')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const submittedData = mockOnSubmit.mock.calls[0][0] as LogicFormData
        expect(submittedData.logicType).toBe(ActivityTypeEnum.LOOP)
        expect(submittedData.name).toBe('Updated Loop')
        expect(submittedData.type).toBe('forEach')
      })
    })

    it('maps converge data correctly and adds logicType on submit', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONVERGE,
            name: 'Test Converge',
            strategy: 'all',
          }}
        />
      )

      const nameInput = screen.getByPlaceholderText(/Enter activity name/i)
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Converge')

      fireEvent.submit(screen.getByTestId('converge-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const submittedData = mockOnSubmit.mock.calls[0][0] as LogicFormData
        expect(submittedData.logicType).toBe(ActivityTypeEnum.CONVERGE)
        expect(submittedData.name).toBe('Updated Converge')
      })
    })

    it('maps wait data correctly and adds logicType on submit', async () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.WAIT,
            name: 'Wait Step',
            duration: 300,
          }}
        />
      )

      fireEvent.submit(screen.getByTestId('wait-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
        const submittedData = mockOnSubmit.mock.calls[0][0] as LogicFormData
        expect(submittedData.logicType).toBe(ActivityTypeEnum.WAIT)
        expect(submittedData.name).toBe('Wait Step')
        expect(submittedData.duration).toBe(300)
      })
    })

    it('defaults wait time fields to 0 when not provided', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.WAIT,
            name: 'Minimal Wait',
          }}
        />
      )

      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(null)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(null)
    })

    it("defaults converge strategy to 'all' when initialData has undefined strategy", () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONVERGE,
            name: 'Converge Node',
          }}
        />
      )

      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toHaveTextContent(
        'All branches reach this step'
      )
    })

    it('defaults loop type to while when not provided', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.LOOP,
            name: 'Loop without type',
          }}
        />
      )

      expect(screen.getByRole('button', { name: 'Type' })).toHaveTextContent('While')
    })
  })

  describe('Initial data mapping', () => {
    it('maps all condition fields from initialData', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONDITION,
            name: 'Condition Node',
            condition: '${value > 10}',
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Condition Node')
    })

    it('maps all loop fields from initialData', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.LOOP,
            name: 'Loop Node',
            type: 'while',
            condition: '${count < 5}',
            maxIterations: 100,
            indexVariable: 'idx',
            itemVariable: 'val',
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Loop Node')
      expect(screen.getByRole('button', { name: 'Type' })).toHaveTextContent('While')
    })

    it('maps all wait fields from initialData', () => {
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.WAIT,
            name: 'Wait Node',
            duration: 184545,
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Wait Node')
      expect(screen.getByRole('spinbutton', { name: /Days/i })).toHaveValue(2)
      expect(screen.getByRole('spinbutton', { name: /Hours/i })).toHaveValue(3)
      expect(screen.getByRole('spinbutton', { name: /Minutes/i })).toHaveValue(15)
      expect(screen.getByRole('spinbutton', { name: /Seconds/i })).toHaveValue(45)
    })

    it('maps all converge fields from initialData', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <LogicNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            logicType: ActivityTypeEnum.CONVERGE,
            name: 'Converge Node',
            strategy: 'any',
            settings: { timeout: 3930, continue_on_failure: false },
            requiredPathCount: 2,
          }}
        />
      )

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Converge Node')
      expect(screen.getByRole('button', { name: 'Continue when criteria' })).toHaveTextContent(
        'Any branches reach this step'
      )

      await user.click(screen.getByRole('tab', { name: 'Settings' }))
      // Converge settings omit timeout; continue_on_failure:false maps to the stop behavior.
      expect(screen.getByRole('button', { name: 'On failure behavior' })).toHaveTextContent(
        'Stop workflow or branch on failure'
      )
    })
  })
})
