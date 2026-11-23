import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsFetchClient } from '../../client'

import { KafkaGroupConflictDialog } from './KafkaGroupConflictDialog'

vi.mock('../../client', () => ({ integrationsFetchClient: { GET: vi.fn() } }))

function renderDialog(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

it('explains the proposed group replacement, supports cancellation, and has no accessibility violations', async () => {
  const user = userEvent.setup()
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { id: 'integration-1', name: 'QA Kafka' },
    response: new Response(),
  } as never)
  const { baseElement } = renderDialog(
    <KafkaGroupConflictDialog
      conflicts={[
        {
          triggerId: 'subscribe',
          triggerName: 'Orders',
          draftGroup: 'draft-B',
          source: {
            trigger_node_id: 'subscribe',
            source_id: 'source-1',
            generation: 1,
            configuration_revision: 1,
            group_id_is_generated: false,
            integration_id: 'integration-1',
            topic: 'orders',
            group_id: 'published-A',
          },
        },
        {
          triggerId: 'alerts',
          triggerName: 'Alerts',
          draftGroup: 'draft-custom',
          source: {
            trigger_node_id: 'alerts',
            source_id: 'source-2',
            generation: 1,
            configuration_revision: 1,
            group_id_is_generated: true,
            integration_id: 'integration-1',
            topic: 'alerts',
            group_id: 'syntara.generated',
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
  expect(await screen.findByText(/QA Kafka \/ orders/)).toBeVisible()
  expect(screen.getByText(/Orders: replace/)).toHaveTextContent('for QA Kafka / orders')
  expect(screen.getByText(/Alerts: clear/)).toHaveTextContent('for QA Kafka / alerts')
  expect(screen.queryByText('syntara.generated')).not.toBeInTheDocument()
  expect(screen.queryByText(/^subscribe:/)).not.toBeInTheDocument()
  expect(await axe(baseElement)).toHaveNoViolations()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalledOnce()
  expect(onConfirm).not.toHaveBeenCalled()
})
