import { render, screen } from '@testing-library/react'
import { use, useState } from 'react'
import { describe, expect, it } from 'vitest'

import { NodeExpandedContext } from './NodeExpandedContext'

function TestConsumer() {
  const context = use(NodeExpandedContext)
  return <div data-testid="context-value">{context === null ? 'null' : String(context[0])}</div>
}

function TestProvider({ initialValue }: { initialValue: boolean }) {
  const state = useState(initialValue)
  return (
    <NodeExpandedContext.Provider value={state}>
      <TestConsumer />
    </NodeExpandedContext.Provider>
  )
}

describe('NodeExpandedContext', () => {
  it('has null as default value', () => {
    render(<TestConsumer />)

    expect(screen.getByTestId('context-value')).toHaveTextContent('null')
  })

  it('provides expanded state when true', () => {
    render(<TestProvider initialValue={true} />)

    expect(screen.getByTestId('context-value')).toHaveTextContent('true')
  })

  it('provides collapsed state when false', () => {
    render(<TestProvider initialValue={false} />)

    expect(screen.getByTestId('context-value')).toHaveTextContent('false')
  })
})
