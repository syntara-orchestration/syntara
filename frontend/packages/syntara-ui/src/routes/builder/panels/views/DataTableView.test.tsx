import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DataTableView } from './DataTableView'

describe('DataTableView', () => {
  it('renders column headers from data keys', () => {
    const data = { hostname: 'server1', port: 8080 }
    render(<DataTableView data={data} ariaLabel="Test data" />)

    expect(screen.getByRole('columnheader', { name: 'hostname' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'port' })).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Test data' })).toBeInTheDocument()
  })

  it('renders cell values', () => {
    const data = { result: 'success', code: 200 }
    render(<DataTableView data={data} ariaLabel="Test data" />)

    expect(screen.getByRole('cell', { name: 'success' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '200' })).toBeInTheDocument()
  })

  it('renders multiple rows for array data', () => {
    const data = [
      { name: 'Alice', age: 30 },
      { name: 'Bob', age: 25 },
    ]
    render(<DataTableView data={data} ariaLabel="Test data" />)

    expect(screen.getByRole('cell', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Bob' })).toBeInTheDocument()
  })

  it('renders empty table when data is null', () => {
    render(<DataTableView data={null} ariaLabel="Test data" />)

    expect(screen.getByRole('grid', { name: 'Test data' })).toBeInTheDocument()
  })

  it('uses the provided ariaLabel', () => {
    const data = { result: 'ok' }
    render(<DataTableView data={data} ariaLabel="Custom label" />)

    expect(screen.getByRole('grid', { name: 'Custom label' })).toBeInTheDocument()
  })

  it('renders a compact table', () => {
    const data = { result: 'ok' }
    render(<DataTableView data={data} ariaLabel="Test data" />)

    expect(screen.getByRole('grid', { name: 'Test data' })).toHaveClass('pf-m-compact')
  })

  it('has no accessibility violations', async () => {
    const data = { hostname: 'server1', port: 8080 }
    const { container } = render(<DataTableView data={data} ariaLabel="Test data" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
