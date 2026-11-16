import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { filteringFetchClient } from '../../../client'
import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'
import { WorkflowValidationContext } from '../WorkflowValidationContext'

import { KafkaSubscribeFilter } from './KafkaSubscribeFilter'
import { zodResolver } from './shared/formSchemaUtils'
import { triggerFormSchema, type TriggerFormData } from './triggerFormSchema'

vi.mock('@patternfly/react-code-editor', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@patternfly/react-code-editor')>()),
  CodeEditor: ({
    code,
    onCodeChange,
    customControls,
    'aria-label': label,
  }: {
    code?: string
    onCodeChange?: (value: string) => void
    customControls?: React.ReactNode
    'aria-label'?: string
  }) => (
    <>
      <textarea aria-label={label} value={code} onChange={(event) => onCodeChange?.(event.target.value)} />
      {customControls}
    </>
  ),
  CodeEditorControl: ({ onClick, 'aria-label': label }: { onClick: () => void; 'aria-label'?: string }) => (
    <button type="button" aria-label={label} onClick={onClick}>
      Expand
    </button>
  ),
}))

const EXPRESSION_LABEL = 'Filter expression (CEL)'
const SAMPLE_LABEL = 'Sample JSON'
const TEST_LABEL = 'Test filter'
const INITIAL_EXPRESSION = '  (input.payload.value.status == "ready")\n && true  '

function Harness({ expression, readOnly = false }: Readonly<{ expression?: string; readOnly?: boolean }>) {
  const form = useForm<TriggerFormData>({
    resolver: zodResolver(triggerFormSchema, undefined, { mode: 'sync' }),
    defaultValues: { triggerType: 'event_subscribe_trigger', filterExpression: expression },
  })
  return (
    <FormProvider {...form}>
      <KafkaSubscribeFilter isReadOnly={readOnly} />
    </FormProvider>
  )
}

function renderFilter(expression?: string, readOnly = false) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ColorSchemeProvider>
        <Harness expression={expression} readOnly={readOnly} />
      </ColorSchemeProvider>
    </QueryClientProvider>
  )
}

async function openFilterTest() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Test filter expression' }))
}

it('authors and clears an optional filter in the always-visible editor', async () => {
  const user = userEvent.setup()
  const { container } = renderFilter()
  const editor = screen.getByRole('textbox', { name: EXPRESSION_LABEL })
  expect(editor).toHaveValue('')
  expect(screen.getByText(/No filter: every otherwise valid message is accepted/)).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: SAMPLE_LABEL })).not.toBeInTheDocument()
  await user.type(editor, 'true')
  expect(editor).toHaveValue('true')
  expect(await axe(container)).toHaveNoViolations()
  await user.clear(editor)
  expect(editor).toHaveFocus()
  expect(editor).toHaveValue('')
  expect(screen.getByText(/No filter: every otherwise valid message is accepted/)).toBeInTheDocument()
})

it('displays saved source exactly and read-only in a version view', async () => {
  const { container } = renderFilter(INITIAL_EXPRESSION, true)
  expect(screen.getByRole('textbox', { name: EXPRESSION_LABEL })).toHaveValue(INITIAL_EXPRESSION)
  expect(screen.getByRole('textbox', { name: EXPRESSION_LABEL })).toHaveAttribute('readonly')
  expect(screen.queryByRole('button', { name: TEST_LABEL })).not.toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})

it('provides accessible CEL guidance from the expression label help', async () => {
  const user = userEvent.setup()
  renderFilter()
  await user.click(screen.getByRole('button', { name: 'More info for Filter expression (CEL)' }))
  expect(await screen.findByRole('link', { name: 'Kafka Subscribe documentation' })).toBeVisible()
  expect(screen.getByText(/Return true to pass a message/)).toBeVisible()
  expect(await axe(screen.getByRole('dialog', { name: EXPRESSION_LABEL }))).toHaveNoViolations()
})

it('opens and closes sample testing with the keyboard without losing focus or sample input', async () => {
  const user = userEvent.setup()
  renderFilter()
  await user.tab()
  expect(screen.getByRole('button', { name: 'More info for Filter expression (CEL)' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('textbox', { name: EXPRESSION_LABEL })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Test filter expression' })).toHaveFocus()
  await user.keyboard('{Enter}')
  expect(screen.getByRole('button', { name: 'Hide filter test' })).toHaveFocus()
  const sample = screen.getByRole('textbox', { name: SAMPLE_LABEL })
  await user.clear(sample)
  await user.type(sample, 'null')
  await user.click(screen.getByRole('button', { name: 'Hide filter test' }))
  expect(screen.getByRole('button', { name: 'Test filter expression' })).toHaveFocus()
  expect(screen.queryByRole('textbox', { name: SAMPLE_LABEL })).not.toBeInTheDocument()
  await user.keyboard(' ')
  expect(screen.getByRole('textbox', { name: SAMPLE_LABEL })).toHaveValue('null')
})

it.each([
  ['match', 'Match'],
  ['no_match', 'No match'],
  ['evaluation_error', 'Evaluation error'],
] as const)('shows %s and sends exact unsaved source with JSON bound directly as input', async (outcome, title) => {
  const post = vi.spyOn(filteringFetchClient, 'POST').mockResolvedValueOnce({
    data: { outcome, error_code: outcome === 'evaluation_error' ? 'filter_wrong_type' : null },
    response: new Response(),
  })
  const user = userEvent.setup()
  renderFilter(INITIAL_EXPRESSION)
  await openFilterTest()
  await user.clear(screen.getByRole('textbox', { name: SAMPLE_LABEL }))
  await user.type(screen.getByRole('textbox', { name: SAMPLE_LABEL }), 'null')
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText(title, { exact: true })).toBeInTheDocument()
  expect(post).toHaveBeenCalledWith('/filtering/test', { body: { expression: INITIAL_EXPRESSION, input: null } })
})

it('blocks malformed JSON before any request and associates the error with the sample', async () => {
  const post = vi.spyOn(filteringFetchClient, 'POST')
  const user = userEvent.setup()
  renderFilter('true')
  await openFilterTest()
  const sample = screen.getByRole('textbox', { name: SAMPLE_LABEL })
  await user.clear(sample)
  await user.type(sample, 'invalid')
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Enter valid JSON before testing the filter')).toBeInTheDocument()
  expect(screen.getByRole('group', { name: SAMPLE_LABEL })).toHaveAccessibleDescription(
    /Enter valid JSON before testing the filter/
  )
  expect(post).not.toHaveBeenCalled()
})

it('surfaces readable compiler errors and locations without discarding source', async () => {
  vi.spyOn(filteringFetchClient, 'POST').mockResolvedValueOnce({
    error: {
      type: 'validation-error',
      title: 'Invalid CEL',
      detail: 'filter_invalid_syntax',
      code: 'filter_invalid_syntax',
      retryable: false,
      line: 2,
      column: 5,
    },
    response: new Response(null, { status: 422 }),
  })
  const user = userEvent.setup()
  const { container } = renderFilter(INITIAL_EXPRESSION)
  await openFilterTest()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Filter configuration error')).toBeInTheDocument()
  const editor = screen.getByRole('textbox', { name: EXPRESSION_LABEL })
  expect(editor).toHaveValue(INITIAL_EXPRESSION)
  expect(editor).toHaveAccessibleDescription(/Syntax error at line 2, column 5/)
  expect(await axe(container)).toHaveNoViolations()
  await user.type(editor, ' ')
  expect(screen.queryByText('Filter configuration error')).not.toBeInTheDocument()
  expect(editor).toHaveAttribute('aria-invalid', 'false')
})

it('retries request failures separately from configuration and evaluation errors', async () => {
  vi.spyOn(filteringFetchClient, 'POST')
    .mockResolvedValueOnce({
      error: { type: 'server', title: 'Unavailable', detail: 'Try again', code: 'INTERNAL_ERROR', retryable: true },
      response: new Response(null, { status: 500 }),
    })
    .mockResolvedValueOnce({ data: { outcome: 'match' }, response: new Response() })
  const user = userEvent.setup()
  renderFilter('true')
  await openFilterTest()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Filter test request failed')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Match', { exact: true })).toBeInTheDocument()
})

it.each([
  ['match', 'Match'],
  ['no_match', 'No match'],
] as const)(
  'hides a previous %s outcome while retesting unchanged input and after a request failure',
  async (outcome, title) => {
    let complete: ((value: Awaited<ReturnType<typeof filteringFetchClient.POST>>) => void) | undefined
    const post = vi
      .spyOn(filteringFetchClient, 'POST')
      .mockResolvedValueOnce({ data: { outcome }, response: new Response() })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve
          })
      )
    const user = userEvent.setup()
    renderFilter('true')
    await openFilterTest()
    await user.click(screen.getByRole('button', { name: TEST_LABEL }))
    expect(await screen.findByText(title, { exact: true })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: TEST_LABEL }))
    expect(await screen.findByText('Testing filter…')).toBeInTheDocument()
    expect(screen.queryByText(title, { exact: true })).not.toBeInTheDocument()
    act(() => {
      complete?.({
        error: { type: 'server', title: 'Unavailable', detail: 'Try again', code: 'INTERNAL_ERROR', retryable: true },
        response: new Response(null, { status: 500 }),
      })
    })
    expect(await screen.findByText('Filter test request failed')).toBeInTheDocument()
    expect(screen.queryByText(title, { exact: true })).not.toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(2)
  }
)

it.each([EXPRESSION_LABEL, SAMPLE_LABEL])('discards pending responses after changing %s', async (label) => {
  let complete: ((value: Awaited<ReturnType<typeof filteringFetchClient.POST>>) => void) | undefined
  vi.spyOn(filteringFetchClient, 'POST').mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      })
  )
  const user = userEvent.setup()
  renderFilter('true')
  await openFilterTest()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Testing filter…')).toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: label }), ' ')
  act(() => {
    complete?.({ data: { outcome: 'match' }, response: new Response() })
  })
  expect(screen.queryByText('Match', { exact: true })).not.toBeInTheDocument()
  expect(screen.queryByText('Testing filter…')).not.toBeInTheDocument()
})

it('clears a completed result when the sample changes', async () => {
  vi.spyOn(filteringFetchClient, 'POST').mockResolvedValueOnce({ data: { outcome: 'match' }, response: new Response() })
  const user = userEvent.setup()
  renderFilter('true')
  await openFilterTest()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Match', { exact: true })).toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: SAMPLE_LABEL }), ' ')
  expect(screen.queryByText('Match', { exact: true })).not.toBeInTheDocument()
})

it('does not attach a stale compiler error to newer source', async () => {
  let complete: ((value: Awaited<ReturnType<typeof filteringFetchClient.POST>>) => void) | undefined
  vi.spyOn(filteringFetchClient, 'POST').mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      })
  )
  const user = userEvent.setup()
  renderFilter('input.')
  await openFilterTest()
  await user.click(screen.getByRole('button', { name: TEST_LABEL }))
  expect(await screen.findByText('Testing filter…')).toBeInTheDocument()
  const editor = screen.getByRole('textbox', { name: EXPRESSION_LABEL })
  await user.clear(editor)
  await user.type(editor, 'true')
  act(() => {
    complete?.({
      error: {
        type: 'validation-error',
        title: 'Invalid CEL',
        detail: 'filter_invalid_syntax',
        code: 'filter_invalid_syntax',
        retryable: false,
      },
      response: new Response(null, { status: 422 }),
    })
  })
  expect(editor).toHaveAttribute('aria-invalid', 'false')
  expect(screen.queryByText('Filter configuration error')).not.toBeInTheDocument()
})

it('shows workflow Save/Verify findings beside the matching filter and hides them after correction', async () => {
  const user = userEvent.setup()
  const { container } = render(
    <WorkflowValidationContext
      value={{
        nodeId: 'kafka',
        errors: [
          {
            nodeId: 'another',
            fieldPath: 'parameters.filter.expression',
            message: 'Other trigger error',
            filterExpression: 'input.',
          },
          {
            nodeId: 'kafka',
            fieldPath: 'parameters.filter.expression',
            message: 'CEL filter: Syntax error at line 1, column 7.',
            filterExpression: 'input.',
          },
        ],
      }}
    >
      <Harness expression="input." />
    </WorkflowValidationContext>
  )
  const editor = screen.getByRole('textbox', { name: EXPRESSION_LABEL })
  expect(editor).toHaveAccessibleDescription(/CEL filter: Syntax error at line 1, column 7/)
  expect(editor).toHaveAttribute('aria-invalid', 'true')
  expect(screen.queryByText('Other trigger error')).not.toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
  await user.clear(editor)
  await user.type(editor, 'true')
  expect(editor).toHaveAttribute('aria-invalid', 'false')
  expect(screen.queryByText('CEL filter: Syntax error at line 1, column 7.')).not.toBeInTheDocument()
})

it('keeps testing guidance in accessible help and retains the sample in the expanded JSON editor', async () => {
  const user = userEvent.setup()
  const { container } = renderFilter('true')
  await openFilterTest()
  expect(screen.queryByText(/Sample testing does not consume Kafka messages/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'More info for Test filter' }))
  expect(await screen.findByText(/Sample testing does not consume Kafka messages/)).toBeVisible()
  await user.keyboard('{Escape}')
  await user.click(screen.getByRole('button', { name: 'Open in new window' }))
  const expanded = screen.getByRole('textbox', { name: 'Sample JSON expanded' })
  await user.clear(expanded)
  await user.type(expanded, 'null')
  await user.keyboard('{Escape}')
  expect(screen.getByRole('textbox', { name: SAMPLE_LABEL })).toHaveValue('null')
  expect(await axe(container)).toHaveNoViolations()
})
