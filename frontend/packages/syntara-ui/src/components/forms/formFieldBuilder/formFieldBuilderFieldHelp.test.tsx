import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'

describe('formFieldBuilderLabelHelp', () => {
  it('renders a help trigger for field settings', () => {
    render(<div>{formFieldBuilderLabelHelp('optionsSource', 'Options source')}</div>)
    expect(screen.getByRole('button', { name: 'More info for Options source' })).toBeInTheDocument()
  })
})
