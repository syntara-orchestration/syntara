import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaGroupConflictDialog } from './KafkaGroupConflictDialog'

it('explains the proposed group replacement, supports cancellation, and has no accessibility violations', async () => {
  const user = userEvent.setup()
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  const { baseElement } = render(
    <KafkaGroupConflictDialog
      conflicts={[
        {
          triggerId: 'subscribe',
          draftGroup: 'draft-B',
          source: {
            trigger_node_id: 'subscribe',
            source_id: 'source-1',
            generation: 1,
            configuration_revision: 1,
            integration_id: 'integration-1',
            topic: 'orders',
            group_id: 'published-A',
          },
        },
      ]}
      isPending={false}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  )
  expect(screen.getByRole('dialog')).toHaveAccessibleName('Use the published consumer groups?')
  expect(screen.getByText('draft-B')).toBeVisible()
  expect(screen.getByText('published-A')).toBeVisible()
  expect(await axe(baseElement)).toHaveNoViolations()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalledOnce()
  expect(onConfirm).not.toHaveBeenCalled()
})
