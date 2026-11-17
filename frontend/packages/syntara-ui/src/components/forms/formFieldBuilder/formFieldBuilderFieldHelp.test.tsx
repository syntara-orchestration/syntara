import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'
import { FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL } from './formFieldBuilderInitialAnswerCopy'

describe('formFieldBuilderLabelHelp', () => {
  it('renders a help trigger for field settings', () => {
    render(<div>{formFieldBuilderLabelHelp('optionsSource', 'Options source')}</div>)
    expect(screen.getByRole('button', { name: 'More info for Options source' })).toBeInTheDocument()
  })

  it('explains that date initial answers must be fully specified', async () => {
    const user = userEvent.setup()
    render(<div>{formFieldBuilderLabelHelp('dateDefaultValue', FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL)}</div>)
    await user.click(screen.getByRole('button', { name: `More info for ${FORM_FIELD_BUILDER_INITIAL_ANSWER_LABEL}` }))
    expect(screen.getByText(/Initial answer can not be partially completed/)).toBeInTheDocument()
  })
})
