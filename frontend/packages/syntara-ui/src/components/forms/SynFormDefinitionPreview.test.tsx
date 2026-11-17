import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum, parseFormDefinition } from '../../forms'

import { SynFormDefinitionPreview } from './SynFormDefinitionPreview'

function renderPreview(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('SynFormDefinitionPreview', () => {
  const definition = parseFormDefinition({
    fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'note', label: 'Note' }],
  })

  it('shows a disabled submit button with a customized label', () => {
    renderPreview(<SynFormDefinitionPreview definition={definition} submitLabel="Send request" />)

    const submitButton = screen.getByRole('button', { name: 'Send request' })
    expect(submitButton).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderPreview(<SynFormDefinitionPreview definition={definition} description="Preview copy" />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
