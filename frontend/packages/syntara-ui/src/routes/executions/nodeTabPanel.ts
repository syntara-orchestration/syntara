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
 * the region is the tabs' panel (role=tabpanel) labelled by the active tab's
 * button (PatternFly composes a tab button id as `pf-tab-{eventKey}-{id}`).
 */
export function nodeTabPanelAttrs(
  hasTabs: boolean,
  idBase: string,
  activeTab: string
): { id: string; role: 'tabpanel'; 'aria-labelledby': string } | Record<string, never> {
  if (!hasTabs) return {}
  return {
    id: nodeTabPanelId(idBase),
    role: 'tabpanel',
    'aria-labelledby': `pf-tab-${activeTab}-${idBase}-${activeTab}`,
  }
}
