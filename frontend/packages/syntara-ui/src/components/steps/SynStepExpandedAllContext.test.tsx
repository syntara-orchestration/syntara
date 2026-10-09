import { render, screen } from '@testing-library/react'
import { use } from 'react'
import { describe, expect, it } from 'vitest'

import { SynStepExpandedAllContext } from './SynStepExpandedAllContext'

function TestConsumer() {
  const context = use(SynStepExpandedAllContext)
  return (
    <div>
      <div data-testid="expand-event">{context.expandAllEvent instanceof EventTarget ? 'valid' : 'invalid'}</div>
      <div data-testid="collapse-event">{context.collapseAllEvent instanceof EventTarget ? 'valid' : 'invalid'}</div>
    </div>
  )
}

describe('SynStepExpandedAllContext', () => {
  it('provides default EventTarget instances', () => {
    render(<TestConsumer />)

    expect(screen.getByTestId('expand-event')).toHaveTextContent('valid')
    expect(screen.getByTestId('collapse-event')).toHaveTextContent('valid')
  })

  it('accepts custom EventTarget instances', () => {
    const customExpand = new EventTarget()
    const customCollapse = new EventTarget()

    render(
      <SynStepExpandedAllContext.Provider value={{ expandAllEvent: customExpand, collapseAllEvent: customCollapse }}>
        <TestConsumer />
      </SynStepExpandedAllContext.Provider>
    )

    expect(screen.getByTestId('expand-event')).toHaveTextContent('valid')
    expect(screen.getByTestId('collapse-event')).toHaveTextContent('valid')
  })
})
