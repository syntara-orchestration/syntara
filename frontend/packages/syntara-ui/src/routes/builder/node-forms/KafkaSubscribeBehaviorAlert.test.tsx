import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaSubscribeBehaviorAlert } from './KafkaSubscribeBehaviorAlert'

const description =
  'Publishing activates the subscription; changes apply on the next publish. The runtime credential authenticates to Kafka, while workflow identity and message offsets are handled automatically.'

describe('Kafka Subscribe behavior alert', () => {
  it('starts collapsed and expands the activation guidance', async () => {
    const user = userEvent.setup()
    const { container } = render(<KafkaSubscribeBehaviorAlert />)
    const toggle = screen.getByRole('button', { name: /info alert details/i })

    expect(screen.getByRole('heading', { name: /Kafka Subscribe behavior/ })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Message delivery behavior' })).not.toBeInTheDocument()
    expect(screen.queryByText(description)).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(toggle)
    expect(screen.getByText(description)).toBeVisible()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(toggle)
    expect(screen.queryByText(description)).not.toBeInTheDocument()
  })
})
