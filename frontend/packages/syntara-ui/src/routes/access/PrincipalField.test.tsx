import { zodResolver } from '@hookform/resolvers/zod'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { detachPromise } from '../../utils/detachPromise'

import { type AssignRoleFormData, assignRoleSchema } from './assignRoleSchema'
import { PrincipalField } from './PrincipalField'

const defaultValues: AssignRoleFormData = {
  principalType: 'user',
  scope: 'system',
  userId: '',
  groupId: '',
  serviceAccountId: '',
  projectId: '',
  roleName: '',
}

function Wrapper({
  name = 'userId',
  options = [
    { value: 'u1', label: 'Alice' },
    { value: 'u2', label: 'Bob' },
  ],
}: {
  name?: 'userId' | 'groupId' | 'serviceAccountId'
  options?: { value: string; label: string }[]
}) {
  const { control, handleSubmit } = useForm<AssignRoleFormData>({
    resolver: zodResolver(assignRoleSchema),
    defaultValues,
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        detachPromise(handleSubmit(() => {})())
      }}
    >
      <PrincipalField
        control={control}
        name={name}
        label="User"
        fieldId="user-select"
        options={options}
        placeholder="Select a user..."
      />
      <button type="submit">Submit</button>
    </form>
  )
}

describe('PrincipalField', () => {
  it('renders label and placeholder', () => {
    render(<Wrapper />)
    expect(screen.getByText('User')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Select a user...')).toBeInTheDocument()
  })

  it('shows options when clicked', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    await user.click(screen.getByPlaceholderText('Select a user...'))

    expect(screen.getByRole('option', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Bob' })).toBeInTheDocument()
  })

  it('selects an option', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    await user.click(screen.getByPlaceholderText('Select a user...'))
    await user.click(screen.getByRole('option', { name: 'Alice' }))

    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
  })

  it('shows validation error on submit without selection', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('User is required')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Wrapper />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with error state', async () => {
    const user = userEvent.setup()
    const { container } = render(<Wrapper />)

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('User is required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
