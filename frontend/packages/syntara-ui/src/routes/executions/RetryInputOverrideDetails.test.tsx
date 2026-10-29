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

const resolvedInputs = { url: 'https://original.example', retries: 1 }

function RetryInputOverrideHarness({
  canEdit = true,
  startEditing = false,
  ...handlers
}: Partial<RetryInputOverrideDetailsProps> &
  Pick<RetryInputOverrideDetailsProps, 'onEdit' | 'onCancel' | 'onSave' | 'onDraftChange'> & {
    startEditing?: boolean
  }) {
  const [isEditing, setIsEditing] = useState(startEditing)
  const [draft, setDraft] = useState<string>()
  const [error, setError] = useState<string>()
  const [savedOverride, setSavedOverride] = useState<Record<string, unknown> | undefined>(handlers.savedOverride)

  return (
    <RetryInputOverrideDetails
      target={target}
      resolvedInputs={resolvedInputs}
      canEdit={canEdit}
      isDisabled={false}
      savedOverride={savedOverride}
      draft={draft}
      error={error}
      isEditing={isEditing}
      onEdit={(targetId, initialDraft) => {
        handlers.onEdit(targetId, initialDraft)
        setDraft(initialDraft)
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

function renderEditor(props?: Partial<RetryInputOverrideDetailsProps> & { startEditing?: boolean }) {
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
  it('explains the workflow edit permission and hides the editor when permission is missing', async () => {
    const { container } = renderEditor({ canEdit: false, startEditing: true })

    expect(screen.getByText('Workflow edit permission is required to override retry inputs.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Input parameters for Deploy step' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('prefills the editor with the full effective input JSON', () => {
    renderEditor({ startEditing: true })

    expect(screen.getByRole('textbox', { name: 'Input parameters for Deploy step' })).toHaveValue(
      JSON.stringify({ url: 'https://original.example', retries: 1 }, null, 2)
    )
    expect(screen.queryByRole('button', { name: 'Reset parameters' })).not.toBeInTheDocument()
  })

  it('saves only the changed keys from the prefilled effective JSON', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderEditor({
      onSave,
      startEditing: true,
      draft: JSON.stringify({ url: 'https://original.example', retries: 1 }, null, 2),
    })

    const editor = screen.getByRole('textbox', { name: 'Input parameters for Deploy step' })
    await user.clear(editor)
    await user.paste('{"url":"https://retry.example","retries":1}')
    await user.click(screen.getByRole('button', { name: 'Save parameters for retry' }))

    expect(onSave).toHaveBeenCalledWith('step-a', { url: 'https://retry.example' })
  })

  it('restores original resolved values in the editor without saving yet', async () => {
    const user = userEvent.setup()
    const onDraftChange = vi.fn()
    renderEditor({
      onDraftChange,
      startEditing: true,
      savedOverride: { url: 'https://retry.example' },
      draft: JSON.stringify({ url: 'https://retry.example', retries: 1 }, null, 2),
    })

    await user.click(screen.getByRole('button', { name: 'Reset parameters' }))

    expect(onDraftChange).toHaveBeenCalledWith(
      'step-a',
      JSON.stringify({ url: 'https://original.example', retries: 1 }, null, 2),
      { url: 'https://original.example', retries: 1 },
      undefined
    )
    expect(screen.getByRole('button', { name: 'Save parameters for retry' })).toBeInTheDocument()
  })

  it('blocks saving unknown input keys and provides a validation message', async () => {
    const user = userEvent.setup()
    renderEditor({ startEditing: true, draft: '{}' })

    const editor = screen.getByRole('textbox', { name: 'Input parameters for Deploy step' })
    await user.clear(editor)
    await user.paste('{"extra":"not allowed"}')

    expect(screen.getByText('Unknown parameter: extra.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save parameters for retry' })).toBeDisabled()
  })
})
