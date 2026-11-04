import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { FallbackDecisionSynSelect } from './FallbackDecisionSynSelect'

describe('FallbackDecisionSynSelect', () => {
  it('renders toggle label from formatToggleLabel', () => {
    render(
      <FallbackDecisionSynSelect
        id="test-fallback"
        helperId="test-fallback-helper"
        value="reject"
        onChange={vi.fn()}
        isDisabled={false}
        options={[
          { value: 'reject', label: 'Reject (default)' },
          { value: 'approve', label: 'Approve' },
        ]}
        parseValue={(val) => (val === 'approve' ? 'approve' : 'reject')}
        formatToggleLabel={(val) => (val === 'reject' ? 'Reject (default)' : 'Approve')}
      />
    )

    expect(screen.getByRole('button', { name: 'Fallback decision' })).toHaveTextContent('Reject (default)')
  })

  it('calls onChange when an option is selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <FallbackDecisionSynSelect
        id="test-fallback"
        helperId="test-fallback-helper"
        value="reject"
        onChange={onChange}
        isDisabled={false}
        options={[
          { value: 'reject', label: 'Reject (default)' },
          { value: 'approve', label: 'Approve' },
        ]}
        parseValue={(val) => (val === 'approve' ? 'approve' : 'reject')}
        formatToggleLabel={(val) => (val === 'reject' ? 'Reject (default)' : 'Approve')}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Fallback decision' }))
    await user.click(screen.getByRole('option', { name: 'Approve' }))

    expect(onChange).toHaveBeenCalledWith('approve')
  })
})
