import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState, type ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RetryFromFailureInputOverrides } from './RetryFromFailureInputOverrides'
import type { RetryInputOverrideTarget } from './retryInputOverrides'

const { mockUseQuery } = vi.hoisted(() => ({ mockUseQuery: vi.fn<(...args: unknown[]) => unknown>() }))

vi.mock('../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]) => mockUseQuery(...args),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const target: RetryInputOverrideTarget = {
  id: 'step-a',
  name: 'Deploy step',
  parameterNames: ['url', 'retries'],
  failedActivityName: 'step-a#iter-2',
}

function InputOverrideHarness(props: ComponentProps<typeof RetryFromFailureInputOverrides>) {
  const [drafts, setDrafts] = useState(props.drafts)
  const handleDraftChange: ComponentProps<typeof RetryFromFailureInputOverrides>['onDraftChange'] = (
    nodeId,
    value,
    parsed,
    error
  ) => {
    props.onDraftChange(nodeId, value, parsed, error)
    setDrafts((current) => ({ ...current, [nodeId]: value }))
  }

  return <RetryFromFailureInputOverrides {...props} drafts={drafts} onDraftChange={handleDraftChange} />
}

function renderOverrides(props?: Partial<ComponentProps<typeof RetryFromFailureInputOverrides>>) {
  const defaultProps: ComponentProps<typeof RetryFromFailureInputOverrides> = {
    executionId: 'execution-123',
    targets: [target],
    workflowDefinitionAvailable: true,
    isDisabled: false,
    drafts: {},
    onDraftChange: vi.fn(),
    ...props,
  }
  return { ...render(<InputOverrideHarness {...defaultProps} />), props: defaultProps }
}

async function expandEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Change inputs before retry' }))
}

async function enterDraft(user: ReturnType<typeof userEvent.setup>, value: string) {
  const editor = screen.getByRole('textbox', { name: 'Parameters to override for Deploy step' })
  await user.clear(editor)
  await user.click(editor)
  await user.paste(value)
}

describe('RetryFromFailureInputOverrides', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ data: { resources: [] }, isPending: false, isError: false })
  })

  it('explains when no selected failure point has configurable parameters', () => {
    renderOverrides({ targets: [] })

    expect(
      screen.getByText('No selected failed steps have configurable input parameters to override.')
    ).toBeInTheDocument()
  })

  it('explains when the workflow definition is unavailable', () => {
    renderOverrides({ targets: [], workflowDefinitionAvailable: false })

    expect(
      screen.getByText('Input overrides are unavailable because this run’s workflow definition could not be loaded.')
    ).toBeInTheDocument()
  })

  it('loads and displays only previous inputs that belong to the target, with an accessible editor', async () => {
    const user = userEvent.setup()
    mockUseQuery.mockReturnValue({
      data: { resources: [{ input_data: { url: 'https://example.test', secret: 'do not show' } }] },
      isPending: false,
      isError: false,
    })
    const { container } = renderOverrides()

    await expandEditor(user)

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      {
        params: {
          path: { execution_id: 'execution-123' },
          query: { activity_name: 'step-a#iter-2', status: 'failed', limit: 1, sort: '-created_at' },
        },
      },
      { retry: false }
    )
    expect(screen.getByText('Inputs from the most recent failed attempt')).toBeInTheDocument()
    expect(screen.getByText(/"url": "https:\/\/example\.test"/, { selector: 'pre' })).toBeInTheDocument()
    expect(screen.queryByText(/secret/, { selector: 'pre' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('uses the base node ID when there is no iteration-specific failed activity', async () => {
    const user = userEvent.setup()
    renderOverrides({ targets: [{ ...target, failedActivityName: undefined }] })

    await expandEditor(user)

    expect(mockUseQuery.mock.lastCall?.[2]).toEqual({
      params: {
        path: { execution_id: 'execution-123' },
        query: { activity_name: 'step-a', status: 'failed', limit: 1, sort: '-created_at' },
      },
    })
  })

  it('shows a loading state while fetching the previous input', async () => {
    const user = userEvent.setup()
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true, isError: false })
    renderOverrides()

    await expandEditor(user)

    expect(screen.getByRole('progressbar', { name: 'Loading inputs for Deploy step' })).toBeInTheDocument()
  })

  it('allows manual entry when loading previous inputs fails', async () => {
    const user = userEvent.setup()
    mockUseQuery.mockReturnValue({ data: undefined, isPending: false, isError: true })
    renderOverrides()

    await expandEditor(user)

    expect(
      screen.getByRole('heading', { name: 'Warning alert: Could not load the previous inputs' })
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Parameters to override for Deploy step' })).toBeEnabled()
  })

  it('shows an empty-state message when no allowed previous values are available', async () => {
    const user = userEvent.setup()
    mockUseQuery.mockReturnValue({
      data: { resources: [{ input_data: { unrelated: 'value' } }] },
      isPending: false,
      isError: false,
    })
    renderOverrides()

    await expandEditor(user)

    expect(screen.getByText('No previous input values are available for this step.')).toBeInTheDocument()
  })

  it('parses valid input and leaves an empty object as no override', async () => {
    const user = userEvent.setup()
    const onDraftChange = vi.fn()
    renderOverrides({ onDraftChange })
    await expandEditor(user)
    await enterDraft(user, '{"url":"https://new.example.test"}')

    expect(onDraftChange).toHaveBeenLastCalledWith(
      'step-a',
      '{"url":"https://new.example.test"}',
      {
        url: 'https://new.example.test',
      },
      undefined
    )
    expect(screen.queryByText('Enter a valid JSON object.')).not.toBeInTheDocument()

    await enterDraft(user, '{}')

    expect(onDraftChange).toHaveBeenLastCalledWith('step-a', '{}', undefined, undefined)
  })

  it('reports malformed JSON and non-object JSON values', async () => {
    const user = userEvent.setup()
    const onDraftChange = vi.fn()
    renderOverrides({ onDraftChange })
    await expandEditor(user)

    await enterDraft(user, '{')
    const invalidJsonMessage = screen.getByText('Enter a valid JSON object.')
    expect(invalidJsonMessage).toBeInTheDocument()
    const editor = screen.getByRole('textbox', { name: 'Parameters to override for Deploy step' })
    const describedById = editor.getAttribute('aria-describedby')
    const describedByElement = describedById ? document.getElementById(describedById) : null
    expect(describedByElement?.textContent).toContain('Enter a valid JSON object.')
    expect(onDraftChange).toHaveBeenLastCalledWith('step-a', '{', undefined, 'Enter a valid JSON object.')

    for (const value of ['null', '[]', '42']) {
      await enterDraft(user, value)
      expect(screen.getByText('Enter a JSON object of parameter names and values.')).toBeInTheDocument()
      expect(onDraftChange).toHaveBeenLastCalledWith(
        'step-a',
        value,
        undefined,
        'Enter a JSON object of parameter names and values.'
      )
    }
  })

  it('rejects one or multiple parameter names outside the workflow definition', async () => {
    const user = userEvent.setup()
    const onDraftChange = vi.fn()
    renderOverrides({ onDraftChange })
    await expandEditor(user)

    await enterDraft(user, '{"unknown":1}')
    expect(screen.getByText('Unknown parameter: unknown.')).toBeInTheDocument()

    await enterDraft(user, '{"unknown":1,"another":2}')
    expect(screen.getByText('Unknown parameters: unknown, another.')).toBeInTheDocument()
  })

  it('disables the editor while the retry is pending', async () => {
    const user = userEvent.setup()
    renderOverrides({ isDisabled: true })

    await expandEditor(user)

    expect(screen.getByRole('textbox', { name: 'Parameters to override for Deploy step' })).toBeDisabled()
  })
})
