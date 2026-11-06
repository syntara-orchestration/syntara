/**
 * Tab/panel ARIA helpers for the node-detail view. Kept in a plain module (not the
 * component file) so the component files export only components (react-refresh) and
 * the panel component stays within its line/complexity budget.
 */

/** Shared id of the tab panel each node-detail tab controls (via aria-controls). */
export function nodeTabPanelId(idBase: string): string {
  return `${idBase}-panel`
}

/**
 * ARIA props for the shared node-detail content region. When the node has tabs,
 * the region is the tabs' panel (role=tabpanel). It names itself with `aria-label`
 * (the active tab's key) rather than `aria-labelledby`: PatternFly generates tab
 * button ids with an internal, unpredictable counter (`pf-tab-{eventKey}-{uid}`),
 * so an `aria-labelledby` reference to a tab button cannot be formed reliably from
 * outside PF. Mirrors the SynUrlTabs standalone-tabpanel pattern. The tab points
 * back at this region via aria-controls (nodeTabPanelId).
 */
export function nodeTabPanelAttrs(
  hasTabs: boolean,
  idBase: string,
  activeTab: string
): { id: string; role: 'tabpanel'; 'aria-label': string } | Record<string, never> {
  if (!hasTabs) return {}
  return {
    id: nodeTabPanelId(idBase),
    role: 'tabpanel',
    'aria-label': activeTab,
  }
}
