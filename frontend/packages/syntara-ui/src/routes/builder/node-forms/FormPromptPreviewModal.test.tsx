import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum, parseFormDefinition } from '../../../forms'
import { FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE } from '../../../forms/formPromptDynamicOptions'

import { FormPromptPreviewModal } from './FormPromptPreviewModal'

function renderPreview(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('FormPromptPreviewModal', () => {
  it('shows preview notice when dynamic options cannot be resolved', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'env',
          label: 'Environment',
          options: {
            source: 'dynamic',
            expression: '${trigger.envs}',
            label_key: 'name',
            value_key: 'id',
          },
        },
      ],
    })

    renderPreview(
      <FormPromptPreviewModal isOpen formDefinition={definition} onClose={vi.fn()} message="Choose an environment" />
    )

    expect(screen.getByText(FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Preview form' })).toBeInTheDocument()
  })

  it('has no accessibility violations when open with static fields', async () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'note', label: 'Note' }],
    })

    const { container } = renderPreview(<FormPromptPreviewModal isOpen formDefinition={definition} onClose={vi.fn()} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when the dynamic-options preview alert is shown', async () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'env',
          label: 'Environment',
          options: {
            source: 'dynamic',
            expression: '${trigger.envs}',
            label_key: 'name',
            value_key: 'id',
          },
        },
      ],
    })

    const { container } = renderPreview(
      <FormPromptPreviewModal isOpen formDefinition={definition} onClose={vi.fn()} message="Choose an environment" />
    )

    expect(screen.getByText(FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE)).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
