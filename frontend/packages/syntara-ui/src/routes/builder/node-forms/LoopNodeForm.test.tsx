import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoopNodeForm, type LoopFormData } from './LoopNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: () => ({ defaults: null, isLoading: false }),
}))

describe('LoopNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders name field', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toBeInTheDocument()
    })

    it('renders type selector', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} />)

      const toggle = screen.getByRole('button', { name: 'Type' })
      expect(toggle).toBeInTheDocument()

      await user.click(toggle)
      expect(screen.getByRole('option', { name: /For each/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /While/i })).toBeInTheDocument()
    })

    it('renders while fields by default', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('spinbutton', { name: /Max iterations/i })).toBeInTheDocument()
      expect(screen.getByRole('group', { name: /Expression builder/i })).toBeInTheDocument()
    })

    it('renders while fields when type is while', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      expect(screen.getByRole('spinbutton', { name: /Max iterations/i })).toBeInTheDocument()
      expect(screen.getByRole('group', { name: /Expression builder/i })).toBeInTheDocument()
    })

    it('renders help icons for while loop parameters', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      const helpButtons = screen.getAllByRole('button', { name: /more info/i })
      // Parameters tab: loop type, max iterations, while conditional expression
      expect(helpButtons.length).toBeGreaterThanOrEqual(3)
    })
  })

  describe('forEach Submission', () => {
    it('submits forEach form even with empty items (permissive schema)', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Loop')
      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Loop',
            type: 'forEach',
          })
        )
      })
    })
  })

  describe('while Submission', () => {
    it('rejects invalid maxIterations values (negative, zero, decimal)', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Invalid Max Loop')
      await user.click(screen.getByRole('button', { name: /Expression editor mode/i }))
      await user.click(await screen.findByRole('option', { name: 'Custom expression' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${running}')

      const maxIterationsInput = screen.getByRole('spinbutton', { name: /Max iterations/i })

      // Test negative value - schema rejects, submit is not called
      await user.clear(maxIterationsInput)
      await user.type(maxIterationsInput, '-1')
      fireEvent.submit(screen.getByTestId('loop-node-form'))
      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })

      mockOnSubmit.mockClear()

      // Test zero value - schema rejects, submit is not called
      await user.clear(maxIterationsInput)
      await user.type(maxIterationsInput, '0')
      fireEvent.submit(screen.getByTestId('loop-node-form'))
      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })

      mockOnSubmit.mockClear()

      // Test decimal value - schema rejects, submit is not called
      await user.clear(maxIterationsInput)
      await user.type(maxIterationsInput, '3.5')
      fireEvent.submit(screen.getByTestId('loop-node-form'))
      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })
    })
  })

  describe('Type Switching', () => {
    it('switches from while to forEach and updates fields', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} />)

      // Initially while
      expect(screen.getByRole('group', { name: /Expression builder/i })).toBeInTheDocument()

      // Switch to forEach
      const toggle = screen.getByRole('button', { name: 'Type' })
      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: /For each/i }))

      // Now should show forEach fields
      expect(screen.getByRole('textbox', { name: /Items expression/i })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /Item variable/i })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /Index variable/i })).toBeInTheDocument()
      expect(screen.queryByRole('group', { name: /Expression builder/i })).not.toBeInTheDocument()
    })
  })

  describe('Initial Data', () => {
    it('pre-populates forEach form with initialData', () => {
      const initialData: Partial<LoopFormData> = {
        name: 'Existing Loop',
        type: 'forEach',
        items: '${myItems}',
        itemVariable: 'elem',
        indexVariable: 'idx',
      }

      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Existing Loop')
      expect(screen.getByPlaceholderText(/trigger.item_list/i)).toHaveValue('${myItems}')
      expect(screen.getByPlaceholderText(/^item$/i)).toHaveValue('elem')
      expect(screen.getByPlaceholderText(/^index$/i)).toHaveValue('idx')
    })

    it('pre-populates while form with initialData', () => {
      const initialData: Partial<LoopFormData> = {
        name: 'Existing While',
        type: 'while',
        condition: '${count < 10}',
        maxIterations: 999,
      }

      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByPlaceholderText(/Enter activity name/i)).toHaveValue('Existing While')
      expect(screen.getByRole('spinbutton', { name: /Max iterations/i })).toHaveValue(999)
    })
  })

  describe('Default Values', () => {
    it('defaults to while type', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: 'Type' })).toHaveTextContent('While')
    })

    it('defaults indexVariable to "index" for forEach', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      expect(screen.getByPlaceholderText(/^index$/i)).toHaveValue('index')
    })

    it('defaults itemVariable to "item" for forEach', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      expect(screen.getByPlaceholderText(/^item$/i)).toHaveValue('item')
    })
  })

  describe('Header Content', () => {
    it('calls onHeaderContentChange with name field', () => {
      const mockOnHeaderContentChange = vi.fn()
      render(<LoopNodeForm onSubmit={mockOnSubmit} onHeaderContentChange={mockOnHeaderContentChange} />)

      expect(mockOnHeaderContentChange).toHaveBeenCalledWith(expect.anything())
    })
  })

  describe('forEach maxIterations', () => {
    it('renders Max iterations input for forEach loops', () => {
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      expect(screen.getByRole('spinbutton', { name: /Max iterations/i })).toBeInTheDocument()
    })

    it('submits forEach with maxIterations when set', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Bounded ForEach')
      await user.type(screen.getByPlaceholderText(/trigger.item_list/i), 'myItems')
      await user.type(screen.getByRole('spinbutton', { name: /Max iterations/i }), '100')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'forEach',
            maxIterations: 100,
          })
        )
      })
    })
  })

  describe('forEach Form Submission', () => {
    it('submits forEach loop data', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Loop')
      await user.type(screen.getByPlaceholderText(/trigger.item_list/i), 'myArray')
      await user.clear(screen.getByPlaceholderText(/^item$/i))
      await user.type(screen.getByPlaceholderText(/^item$/i), 'element')
      await user.clear(screen.getByPlaceholderText(/^index$/i))
      await user.type(screen.getByPlaceholderText(/^index$/i), 'i')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Loop',
            type: 'forEach',
            items: 'myArray',
            itemVariable: 'element',
            indexVariable: 'i',
          })
        )
      })
    })

    it('submits without logicType field', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Another Loop')
      await user.type(screen.getByPlaceholderText(/trigger.item_list/i), 'items')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as LoopFormData
        expect(submittedData).not.toHaveProperty('logicType')
        expect(submittedData.type).toBe('forEach')
      })
    })

    it('cleans data for forEach (omits condition and maxIterations when not set)', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'forEach' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Clean Loop')
      await user.type(screen.getByPlaceholderText(/trigger.item_list/i), 'cleanItems')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as LoopFormData
        expect(submittedData).not.toHaveProperty('condition')
        expect(submittedData).not.toHaveProperty('maxIterations')
        expect(submittedData.items).toBe('cleanItems')
      })
    })
  })

  describe('while Form Submission', () => {
    it('submits while loop data with all optional parameters', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'While Loop')

      await user.type(screen.getByRole('spinbutton', { name: /Max iterations/i }), '500')

      await user.click(screen.getByRole('button', { name: /Expression editor mode/i }))
      await user.click(await screen.findByRole('option', { name: 'Custom expression' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${x < 100}')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'While Loop',
            type: 'while',
            condition: '${x < 100}',
            maxIterations: 500,
          })
        )
      })
    })

    it('submits while loop data without maxIterations', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Simple While')

      await user.click(screen.getByRole('button', { name: /Expression editor mode/i }))
      await user.click(await screen.findByRole('option', { name: 'Custom expression' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${running}')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as LoopFormData
        expect(submittedData.type).toBe('while')
        expect(submittedData.condition).toBe('${running}')
        expect(submittedData).not.toHaveProperty('maxIterations')
      })
    }, 10_000)

    it('cleans data for while (no items, indexVariable, or itemVariable)', async () => {
      const user = userEvent.setup()
      renderWithHeader(<LoopNodeForm onSubmit={mockOnSubmit} initialData={{ type: 'while' }} />)

      await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Clean While')
      await user.click(screen.getByRole('button', { name: /Expression editor mode/i }))
      await user.click(await screen.findByRole('option', { name: 'Custom expression' }))
      const rawInput = screen.getByLabelText(/Raw expression/i)
      await user.click(rawInput)
      await user.paste('${running}')

      fireEvent.submit(screen.getByTestId('loop-node-form'))

      await waitFor(() => {
        const submittedData = mockOnSubmit.mock.calls[0][0] as LoopFormData
        expect(submittedData).not.toHaveProperty('items')
        expect(submittedData).not.toHaveProperty('itemVariable')
        expect(submittedData).not.toHaveProperty('indexVariable')
        expect(submittedData.condition).toBe('${running}')
      })
    }, 10_000)
  })
})
