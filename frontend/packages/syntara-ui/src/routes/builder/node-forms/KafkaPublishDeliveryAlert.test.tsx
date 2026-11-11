import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaPublishDeliveryAlert } from './KafkaPublishDeliveryAlert'

describe('Kafka Publish delivery alert', () => {
  it('starts expanded and supports keyboard collapse and expansion without losing the warning', async () => {
    const user = userEvent.setup()
    const { container } = render(<KafkaPublishDeliveryAlert />)
    const toggle = screen.getByRole('button', { name: 'Message delivery behavior' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Kafka acknowledgment confirms broker receipt/)).toBeVisible()
    expect(screen.getByRole('note', { name: 'Kafka Publish delivery details' })).toBeVisible()
    act(() => toggle.focus())
    await user.keyboard('{Enter}')
    expect(toggle).toHaveFocus()
    expect(screen.queryByText(/Kafka acknowledgment confirms broker receipt/)).not.toBeInTheDocument()
    expect(screen.queryByRole('note', { hidden: true })).not.toBeInTheDocument()
    expect(toggle).not.toHaveAttribute('aria-controls')
    expect(await axe(container)).toHaveNoViolations()
    await user.keyboard(' ')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Timeout or cancellation may leave delivery unconfirmed/)).toBeVisible()
  })
})
