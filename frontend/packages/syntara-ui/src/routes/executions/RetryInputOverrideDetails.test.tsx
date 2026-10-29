import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RetryInputOverrideDetails } from './RetryInputOverrideDetails'
import type { RetryInputOverrideDetailsProps } from './RetryInputOverrideDetails'
import type { RetryInputOverrideTarget } from './retryInputOverrides'

const target: RetryInputOverrideTarget = {
  id: 'step-a',
  name: 'Deploy step',
  parameterNames: ['url', 'retries'],
}

function RetryInputOverrideHarness({
  canEdit = true,
  ...handlers
}: Partial<RetryInputOverrideDetailsProps> &
  Pick<RetryInputOverrideDetailsProps, 'onEdit' | 'onCancel' | 'onSave' | 'onDraftChange'>) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState<string>()
  const [error, setError] = useState<string>()
  const [savedOverride, setSavedOverride] = useState<Record<string, unknown>>()

  return (
    <RetryInputOverrideDetails
      target={target}
      canEdit={canEdit}
      isDisabled={false}
      savedOverride={savedOverride}
      draft={draft}
      error={error}
      isEditing={isEditing}
      onEdit={(targetId) => {
        handlers.onEdit(targetId)
        setDraft(JSON.stringify(savedOverride ?? {}, null, 2))
        setIsEditing(true)
      }}
      onCancel={(targetId) => {
        handlers.onCancel(targetId)
        setDraft(undefined)
        setError(undefined)
        setIsEditing(false)
      }}
      onSave={(targetId, overrides) => {
        handlers.onSave(targetId, overrides)
        setSavedOverride(overrides)
        setDraft(undefined)
        setError(undefined)
        setIsEditing(false)
      }}
      onDraftChange={(targetId, value, parsed, nextError) => {
        handlers.onDraftChange(targetId, value, parsed, nextError)
        setDraft(value)
        setError(nextError)
      }}
    />
  )
}

function renderEditor(props?: Partial<RetryInputOverrideDetailsProps>) {
  return render(
    <RetryInputOverrideHarness
      onEdit={vi.fn()}
      onCancel={vi.fn()}
      onSave={vi.fn()}
      onDraftChange={vi.fn()}
      {...props}
    />
  )
}

describe('RetryInputOverrideDetails', () => {
  it('explains the workflow edit permission and hides edit controls when permission is missing', async () => {
    const { container } = renderEditor({ canEdit: false })

    expect(screen.getByText('Workflow edit permission is required to override retry inputs.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit inputs' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('saves a valid retry-only override and returns to the edit control', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderEditor({ onSave })

    await user.click(screen.getByRole('button', { name: 'Edit inputs' }))
    expect(screen.getByText(/Enter only the parameter keys to change/)).toBeInTheDocument()
    const editor = screen.getByRole('textbox', { name: 'Input overrides for Deploy step' })
    await user.clear(editor)
    await user.paste('{"url":"https://retry.example"}')
    await user.click(screen.getByRole('button', { name: 'Save inputs' }))

    expect(onSave).toHaveBeenCalledWith('step-a', { url: 'https://retry.example' })
    expect(screen.getByRole('button', { name: 'Edit inputs' })).toBeInTheDocument()
  })

  it('blocks saving unknown input keys and provides a validation message', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: 'Edit inputs' }))
    const editor = screen.getByRole('textbox', { name: 'Input overrides for Deploy step' })
    await user.clear(editor)
    await user.paste('{"extra":"not allowed"}')

    expect(screen.getByText('Unknown parameter: extra.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save inputs' })).toBeDisabled()
  })
})
