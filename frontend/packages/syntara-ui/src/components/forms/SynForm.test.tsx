import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'
import { renderWithForm } from '../../test/renderWithForm'

import { SynForm } from './SynForm'
import { SynTextField } from './SynTextField'

const schema = z.object({ name: z.string().min(1, 'Name is required') })
type FormData = z.infer<typeof schema>

describe('SynForm', () => {
  it('lets Syn* fields omit control when wrapped in SynForm', async () => {
    const user = userEvent.setup()

    renderWithForm<FormData>({ schema, defaultValues: { name: '' } }, (form) => (
      <SynForm form={form}>
        <SynTextField name="name" label="Group name" />
        <button type="button" onClick={form.handleSubmit(vi.fn())}>
          Submit
        </button>
      </SynForm>
    ))

    expect(screen.getByRole('textbox', { name: 'Group name' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Name is required')).toBeInTheDocument()
  })

  it('works with useSynForm', () => {
    function FormHost() {
      const form = useSynForm({ schema, defaultValues: { name: '' } })

      return (
        <SynForm form={form}>
          <SynTextField name="name" label="Group name" />
        </SynForm>
      )
    }

    render(<FormHost />)

    expect(screen.getByRole('textbox', { name: 'Group name' })).toBeInTheDocument()
  })
})
