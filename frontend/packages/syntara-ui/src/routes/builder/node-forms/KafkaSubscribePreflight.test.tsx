import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { workflowFetchClient } from '../../../client'
import { useBuilderPermissions } from '../useBuilderPermissions'

import { KafkaSubscribePreflight } from './KafkaSubscribePreflight'

vi.mock('../useBuilderPermissions', () => ({ useBuilderPermissions: vi.fn() }))
vi.mock('../../../hooks/useMutationErrorHandler', () => ({ useMutationErrorHandler: () => () => vi.fn() }))

const parameters = {
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: '22222222-2222-4222-8222-222222222222',
  topic: 'orders',
}
const verified = {
  success: true,
  checked_at: '2026-06-15T10:00:00Z',
  connection: 'verified',
  topic_metadata: 'verified',
  topic_read: 'unverified',
  group_access: 'unverified',
} as const

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.mocked(useBuilderPermissions).mockReturnValue({
    canEdit: true,
    tooltips: { edit: 'Workflow update permission required' },
  } as never)
})

it('discards an old pending response when the configuration key changes', async () => {
  let complete: ((value: Awaited<ReturnType<typeof workflowFetchClient.POST>>) => void) | undefined
  vi.spyOn(workflowFetchClient, 'POST').mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      })
  )
  const user = userEvent.setup()
  const { rerender } = render(
    <KafkaSubscribePreflight key="orders" workflowId="workflow-1" parameters={parameters} isReadOnly={false} />,
    { wrapper }
  )
  await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
  expect(await screen.findByText('Checking runtime access…')).toBeInTheDocument()

  rerender(
    <KafkaSubscribePreflight
      key="other"
      workflowId="workflow-1"
      parameters={{ ...parameters, topic: 'other' }}
      isReadOnly={false}
    />
  )
  complete?.({ data: verified, response: new Response() })

  await waitFor(() => expect(screen.queryByText('Checking runtime access…')).not.toBeInTheDocument())
  expect(screen.queryByText('Connection and topic metadata checked')).not.toBeInTheDocument()
})

it('presents retryable API errors through the shared error state', async () => {
  const post = vi
    .spyOn(workflowFetchClient, 'POST')
    .mockResolvedValueOnce({
      error: { title: 'Service unavailable', status: 500, retryable: true },
      response: new Response(null, { status: 500 }),
    })
    .mockResolvedValueOnce({ data: verified, response: new Response() })
  const user = userEvent.setup()
  const { container } = render(
    <KafkaSubscribePreflight workflowId="workflow-1" parameters={parameters} isReadOnly={false} />,
    { wrapper }
  )
  await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
  expect(await screen.findByText('Unable to test Kafka runtime access')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('Connection and topic metadata checked')).toBeInTheDocument()
  expect(post).toHaveBeenCalledTimes(2)
  expect(await axe(container)).toHaveNoViolations()
})
