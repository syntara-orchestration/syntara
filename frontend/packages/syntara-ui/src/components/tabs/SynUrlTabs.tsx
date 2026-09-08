import { Tabs, type TabsProps } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import React, { useEffect, useId } from 'react'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { useUrlTab } from '../../hooks/useUrlTab'
import { detachPromise } from '../../utils/detachPromise'

type UrlTabsProps = Omit<TabsProps, 'activeKey' | 'onSelect' | 'ref' | 'children'> & {
  /**
   * Tab children (`<Tab>` elements). Typed as `ReactNode` to accept pre-cloned Tab arrays from
   * callers like `SynListPanelTabs`; cast to PF's `TabsChild` when forwarded to `<Tabs>`.
   */
  children?: React.ReactNode
  /** Base path used to derive the active tab from the URL (e.g. `/system-administration/settings`). */
  basePath: string
  /** Tab key used when the URL has no tab segment (default: `'details'`). */
  defaultTab?: string
  /**
   * When provided, the component redirects (via `replace`) to `defaultTab`
   * if the current URL tab segment is not in this list.
   * Use for pages whose tabs are loaded dynamically (e.g. from an API).
   */
  validTabs?: string[]
  /**
   * When true, tab switches go through the `requestNavigation` unsaved-changes guard
   * instead of navigating directly. Use on pages where a tab may have unsaved state.
   */
  guardUnsavedChanges?: boolean
  /**
   * Optional callback to render the active tab's content inside a proper `role="tabpanel"` wrapper.
   *
   * For Tabs whose children have no own content (URL-routing pattern), PF would otherwise generate
   * `aria-controls` attributes pointing to non-existent panel elements — an ARIA violation.
   * When provided, the active tab's panel is rendered here; remaining tabs get hidden stubs.
   * When omitted, empty stubs are still rendered for childless Tabs to satisfy `aria-controls`.
   *
   * Tabs whose children already have content (the legacy inline-panel pattern) are not affected —
   * PF manages those panels naturally and no stubs are generated for them.
   *
   * **TanStack Router migration:** pass `renderPanel={() => <Outlet />}` once routes are nested.
   *
   * Note: stubs are also skipped for Tabs whose `tabContentId` was pre-set by the caller (e.g.
   * `SynListPanelTabs` which wires panels to `SynListPanelView` via context).
   */
  renderPanel?: (activeTab: string) => React.ReactNode
}

export function SynUrlTabs({
  basePath,
  defaultTab = 'details',
  validTabs,
  children,
  guardUnsavedChanges,
  renderPanel,
  ...tabsProps
}: UrlTabsProps) {
  const uid = useId()
  const [activeTab, goToTab] = useUrlTab(basePath, defaultTab)
  const navigate = useNavigate()

  // validTabs arrives asynchronously (from an API); redirect when the URL tab is absent from the
  // list is an async-prop side-effect, not a user event — useEffect is correct here.
  // Deferred via requestAnimationFrame so the router can finish transitioning to a
  // sibling route (e.g. $userId/edit) before this component decides to redirect.
  // Without the defer, the stale component's redirect races with the route transition.
  useEffect(() => {
    if (!validTabs || validTabs.length === 0) return
    if (validTabs.includes(activeTab)) return
    const id = requestAnimationFrame(() => {
      const target = validTabs.includes(defaultTab) ? defaultTab : validTabs[0]
      detachPromise(navigate({ to: `${basePath}/${target}`, replace: true }))
    })
    return () => cancelAnimationFrame(id)
  }, [validTabs, activeTab, defaultTab, basePath, navigate])

  useEffect(() => {
    const blurStaleTab = () => {
      if (document.activeElement instanceof HTMLElement && document.activeElement.getAttribute('role') === 'tab') {
        document.activeElement.blur()
      }
    }
    globalThis.addEventListener('popstate', blurStaleTab)
    return () => globalThis.removeEventListener('popstate', blurStaleTab)
  }, [])

  const { requestNavigation } = useUnsavedChanges()

  const handleSelect = (_event: React.MouseEvent<HTMLElement, MouseEvent>, key: string | number) => {
    if (guardUnsavedChanges) {
      requestNavigation(`${basePath}/${String(key)}`)
    } else {
      goToTab(String(key))
    }
  }

  // Classify each Tab child. Tabs that already have their own panel content (children prop set) let
  // PF manage panel rendering naturally — no injection needed. Tabs that don't have own content
  // (URL-routing pattern) need external panel stubs, UNLESS they already have tabContentId set by
  // the caller (e.g. SynListPanelTabs wiring panels via context).
  type TabEntry = { key: string; needsStub: boolean }
  const tabEntries: TabEntry[] = React.Children.toArray(children)
    .filter(React.isValidElement)
    .map((child) => {
      const tab = child as React.ReactElement<{
        eventKey: string | number
        children?: React.ReactNode
        tabContentId?: string
      }>
      const key = String(tab.props.eventKey)
      const hasOwnContent = Boolean(tab.props.children)
      const hasExternalPanel = Boolean(tab.props.tabContentId)
      return { key, needsStub: !hasOwnContent && !hasExternalPanel }
    })
    .filter((e) => e.key)

  const stubKeys = tabEntries.filter((e) => e.needsStub).map((e) => e.key)

  // Inject tabContentId only into Tabs that need stubs (childless + no pre-set external ID).
  // Cast via `unknown` because React.Children.map's inferred type is broader than PF's TabsChild.
  const clonedChildren = (React.Children.map(children, (child) => {
    if (!React.isValidElement(child)) return child
    const tab = child as React.ReactElement<{
      eventKey: string | number
      children?: React.ReactNode
      tabContentId?: string
    }>
    const key = String(tab.props.eventKey)
    const needsStub = stubKeys.includes(key)
    if (!needsStub) return child
    return React.cloneElement(tab, { tabContentId: `${uid}-panel-${key}` })
  }) ?? children) as unknown as TabsProps['children'] // React.Children.map returns ReactNode which doesn't satisfy PF's TabsChild type constraint

  return (
    <>
      <Tabs activeKey={activeTab} onSelect={handleSelect} {...tabsProps}>
        {clonedChildren}
      </Tabs>
      {stubKeys.map((key) => (
        // Standalone panel element satisfying PF's generated aria-controls for childless Tabs.
        // aria-label uses the eventKey as a fallback accessible name; callers needing richer labels
        // should pass renderPanel (which provides the full panel) or use SynListPanelView with
        // tabKey/tabLabel for SynListPanel compound usage.
        <section
          key={key}
          id={`${uid}-panel-${key}`}
          role="tabpanel"
          aria-label={key}
          hidden={key !== activeTab ? true : undefined}
        >
          {renderPanel && key === activeTab ? renderPanel(activeTab) : null}
        </section>
      ))}
    </>
  )
}
