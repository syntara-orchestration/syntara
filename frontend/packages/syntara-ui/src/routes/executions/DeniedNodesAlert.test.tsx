import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DeniedNodesAlert } from './DeniedNodesAlert'

const deniedNodes = [
  { node_id: 'restart_service', kind: 'http_request', denied_by: 'no-restarts-in-production' },
  { node_id: 'run_script' },
]

describe('DeniedNodesAlert', () => {
  it('renders nothing when there are no denied nodes', () => {
    const { container } = render(<DeniedNodesAlert deniedNodes={[]} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when denied_nodes is null', () => {
    const { container } = render(<DeniedNodesAlert deniedNodes={null} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders a "Denied nodes" section for a non-empty list', () => {
    render(<DeniedNodesAlert deniedNodes={deniedNodes} />)

    expect(screen.getByTestId('denied-nodes-alert')).toBeInTheDocument()
    expect(screen.getByText('Denied nodes')).toBeInTheDocument()
  })

  it('shows the node kind and the denying policy', () => {
    render(<DeniedNodesAlert deniedNodes={deniedNodes} />)

    expect(screen.getByText('http_request')).toBeInTheDocument()
    expect(screen.getByText('Denied by policy "no-restarts-in-production"')).toBeInTheDocument()
  })

  it('falls back to a generic policy line when denied_by is missing', () => {
    render(<DeniedNodesAlert deniedNodes={deniedNodes} />)

    expect(screen.getByText('Denied by policy')).toBeInTheDocument()
  })

  it('resolves node names from the definition when available', () => {
    render(<DeniedNodesAlert deniedNodes={deniedNodes} nameMap={new Map([['restart_service', 'Restart Service']])} />)

    expect(screen.getByText('Restart Service')).toBeInTheDocument()
    // No name in the map: falls back to the node id
    expect(screen.getByText('run_script')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<DeniedNodesAlert deniedNodes={deniedNodes} />)

    const results = await axe(container)

    expect(results).toHaveNoViolations()
  })
})
