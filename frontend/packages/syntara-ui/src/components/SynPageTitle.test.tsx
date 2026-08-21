import { render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPageTitle } from './SynPageTitle'

describe('SynPageTitle', () => {
  afterEach(() => {
    document.title = ''
  })

  it('sets document.title with a single segment', () => {
    render(<SynPageTitle segments={['Workflows']} />)
    expect(document.title).toBe('Workflows | Syntara')
  })

  it('sets document.title with multiple segments, most-specific first', () => {
    render(<SynPageTitle segments={['My Workflow', 'Workflows']} />)
    expect(document.title).toBe('My Workflow | Workflows | Syntara')
  })

  it('renders just the app title when segments is empty', () => {
    render(<SynPageTitle segments={[]} />)
    expect(document.title).toBe('Syntara')
  })

  it('filters out null and undefined segments', () => {
    render(<SynPageTitle segments={[null, undefined, 'Workflows']} />)
    expect(document.title).toBe('Workflows | Syntara')
  })

  it('filters out blank/whitespace-only segments', () => {
    render(<SynPageTitle segments={['  ', 'Workflows']} />)
    expect(document.title).toBe('Workflows | Syntara')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynPageTitle segments={['Workflows']} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
