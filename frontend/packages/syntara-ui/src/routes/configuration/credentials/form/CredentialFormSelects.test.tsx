import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CredentialTypeSelect, ProjectSelect } from './CredentialFormSelects'

describe('CredentialFormSelects', () => {
  describe('ProjectSelect', () => {
    const projects = Array.from({ length: 20 }, (_, i) => ({
      id: `proj-${i + 1}`,
      name: `Project ${i + 1}`,
    }))

    it('opens a menu with many project options', async () => {
      const user = userEvent.setup()
      render(<ProjectSelect value="" onChange={vi.fn()} projects={projects} />)

      await user.click(screen.getByRole('button', { name: 'Credential project' }))

      expect(screen.getByRole('listbox')).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Project 1' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Project 20' })).toBeInTheDocument()
    })

    it('calls onChange when a project is selected', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      render(<ProjectSelect value="" onChange={onChange} projects={projects.slice(0, 3)} />)

      await user.click(screen.getByRole('button', { name: 'Credential project' }))
      await user.click(screen.getByRole('option', { name: 'Project 2' }))

      expect(onChange).toHaveBeenCalledWith('proj-2')
    })

    it('closes when scrolling outside the open menu', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <ProjectSelect value="" onChange={vi.fn()} projects={projects} />
          <p>Modal body</p>
        </div>
      )

      await user.click(screen.getByRole('button', { name: 'Credential project' }))
      expect(screen.getByRole('listbox')).toBeInTheDocument()

      act(() => {
        screen.getByText('Modal body').dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
      })

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })
    })
  })

  describe('CredentialTypeSelect', () => {
    const types = Array.from({ length: 20 }, (_, i) => ({
      id: `type-${i + 1}`,
      name: `Credential Type ${i + 1}`,
    }))

    it('opens a menu with many credential type options', async () => {
      const user = userEvent.setup()
      render(<CredentialTypeSelect types={types} selectedTypeId="" onSelect={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: 'Credential type' }))

      expect(screen.getByRole('listbox', { name: 'Credential type options' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Credential Type 1' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Credential Type 20' })).toBeInTheDocument()
    })

    it('calls onSelect when a type is selected', async () => {
      const user = userEvent.setup()
      const onSelect = vi.fn()
      render(<CredentialTypeSelect types={types.slice(0, 3)} selectedTypeId="" onSelect={onSelect} />)

      await user.click(screen.getByRole('button', { name: 'Credential type' }))
      await user.click(screen.getByRole('option', { name: 'Credential Type 2' }))

      expect(onSelect).toHaveBeenCalledWith(expect.anything(), 'type-2')
    })

    it('passes type descriptions to SelectOption', async () => {
      const user = userEvent.setup()
      const typesWithDescriptions = [
        { id: 'type-1', name: 'HTTP Bearer Token', description: 'Authenticate with a bearer token.' },
        { id: 'type-2', name: 'SSH Key', description: '   ' },
      ]
      render(<CredentialTypeSelect types={typesWithDescriptions} selectedTypeId="" onSelect={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: 'Credential type' }))
      const listbox = screen.getByRole('listbox', { name: 'Credential type options' })
      expect(listbox).toHaveTextContent('Authenticate with a bearer token.')
    })
  })
})
