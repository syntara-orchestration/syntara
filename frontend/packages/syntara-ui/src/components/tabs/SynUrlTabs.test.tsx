import { Tab } from '@patternfly/react-core'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { routerTestState } from '../../test/setup'

import { SynUrlTabs } from './SynUrlTabs'

describe('SynUrlTabs', () => {
  beforeEach(() => {
    routerTestState.pathname = '/base/tab-a'
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynUrlTabs basePath="/base" defaultTab="tab-a" aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('sets active tab from URL path segment', () => {
    render(
      <SynUrlTabs basePath="/base" aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    expect(screen.getByRole('tab', { name: 'Tab A' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Tab B' })).toHaveAttribute('aria-selected', 'false')
  })

  it('navigates to the correct URL when a tab is clicked', async () => {
    const user = userEvent.setup()
    render(
      <SynUrlTabs basePath="/base" aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    await user.click(screen.getByRole('tab', { name: 'Tab B' }))

    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/base/tab-b' })
  })

  it('uses defaultTab when URL has no tab segment', () => {
    routerTestState.pathname = '/base'
    render(
      <SynUrlTabs basePath="/base" defaultTab="tab-b" aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    expect(screen.getByRole('tab', { name: 'Tab B' })).toHaveAttribute('aria-selected', 'true')
  })

  it('redirects to defaultTab when URL tab is not in validTabs', async () => {
    routerTestState.pathname = '/base/invalid'
    render(
      <SynUrlTabs basePath="/base" defaultTab="tab-a" validTabs={['tab-a', 'tab-b']} aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    await act(() => new Promise((r) => requestAnimationFrame(r)))
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/base/tab-a', replace: true })
  })

  it('does not redirect when URL tab is valid', () => {
    render(
      <SynUrlTabs basePath="/base" defaultTab="tab-a" validTabs={['tab-a', 'tab-b']} aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    expect(routerTestState.navigate).not.toHaveBeenCalled()
  })

  it('redirects to first validTab when no defaultTab is provided', async () => {
    routerTestState.pathname = '/base'
    render(
      <SynUrlTabs basePath="/base" validTabs={['first', 'second']} aria-label="Test tabs">
        <Tab eventKey="first" title="First">
          Content
        </Tab>
        <Tab eventKey="second" title="Second">
          Content
        </Tab>
      </SynUrlTabs>
    )

    await act(() => new Promise((r) => requestAnimationFrame(r)))
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/base/first', replace: true })
  })

  it('passes through additional Tabs props', () => {
    render(
      <SynUrlTabs basePath="/base" defaultTab="tab-a" aria-label="Custom label" isBox>
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
      </SynUrlTabs>
    )

    expect(screen.getByRole('tab', { name: 'Tab A' })).toBeInTheDocument()
  })

  it('blurs focused tab on popstate (browser back/forward)', () => {
    render(
      <SynUrlTabs basePath="/base" aria-label="Test tabs">
        <Tab eventKey="tab-a" title="Tab A">
          Content A
        </Tab>
        <Tab eventKey="tab-b" title="Tab B">
          Content B
        </Tab>
      </SynUrlTabs>
    )

    const tabA = screen.getByRole('tab', { name: 'Tab A' })
    tabA.focus()
    expect(tabA).toHaveFocus()

    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    expect(tabA).not.toHaveFocus()
  })
})
