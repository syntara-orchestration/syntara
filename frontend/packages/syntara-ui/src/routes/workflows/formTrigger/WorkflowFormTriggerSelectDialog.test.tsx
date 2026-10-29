import { TriggerTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { parseFormDefinition } from '../../../forms'
import type { WorkflowRunTrigger } from '../resolveWorkflowRunTrigger'

import { WorkflowFormTriggerSelectDialog } from './WorkflowFormTriggerSelectDialog'

const triggers: WorkflowRunTrigger[] = [
  {
    triggerNodeId: 'form-a',
    triggerName: 'Intake alpha',
    triggerType: TriggerTypeEnum.FORM_TRIGGER,
    hasTriggerReferences: false,
    formTrigger: {
      definition: parseFormDefinition({
        fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }],
      }),
    },
  },
  {
    triggerNodeId: 'form-b',
    triggerName: 'Intake beta',
    triggerType: TriggerTypeEnum.FORM_TRIGGER,
    hasTriggerReferences: false,
    formTrigger: {
      definition: parseFormDefinition({
        fields: [{ type: 'text', value_name: 'b', label: 'B', required: true }],
      }),
    },
  },
]

describe('WorkflowFormTriggerSelectDialog', () => {
  it('has no accessibility violations when open', async () => {
    const { container } = render(
      <WorkflowFormTriggerSelectDialog isOpen triggers={triggers} onClose={vi.fn()} onSelect={vi.fn()} />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('lists form steps under the Run workflow menu group', () => {
    render(<WorkflowFormTriggerSelectDialog isOpen triggers={triggers} onClose={vi.fn()} onSelect={vi.fn()} />)

    expect(screen.getByRole('dialog', { name: 'Run workflow' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Intake alpha' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Intake beta' })).toBeInTheDocument()
  })

  it('calls onSelect with the chosen form step', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<WorkflowFormTriggerSelectDialog isOpen triggers={triggers} onClose={vi.fn()} onSelect={onSelect} />)

    await user.click(screen.getByRole('menuitem', { name: 'Intake beta' }))
    expect(onSelect).toHaveBeenCalledWith(triggers[1])
  })

  it('calls onClose when the dialog is dismissed', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<WorkflowFormTriggerSelectDialog isOpen triggers={triggers} onClose={onClose} onSelect={vi.fn()} />)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
