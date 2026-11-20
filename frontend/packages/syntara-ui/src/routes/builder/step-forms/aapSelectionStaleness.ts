import type { useAAPBrowser } from '../../../hooks/useAAPBrowser'

/** The parts of the AAP browser result that staleness detection depends on. */
export type AAPStalenessBrowser = Pick<
  ReturnType<typeof useAAPBrowser>,
  'isActive' | 'error' | 'loadingOrgs' | 'loadingTemplates' | 'organizations' | 'templates'
>

export type AAPSelectionStaleness = {
  /** True when the selected organization is absent from the loaded org list. */
  organization: boolean
  /** True when the selected template is absent from the loaded template list. */
  template: boolean
}

/**
 * Determine which saved selections the currently loaded AAP resource lists no
 * longer offer.
 *
 * The lists are fetched per credential, so a selection that survives a
 * credential switch is retained, while one the new credential cannot see is
 * stale: a stale organization invalidates the template selection with it, and
 * a stale template clears only itself. Staleness is reported only on positive
 * evidence — never while lists are loading, while browsing is inactive, or
 * when a query has errored; transient failures surface through the browser
 * error alert instead.
 */
export function getAAPSelectionStaleness(
  browser: AAPStalenessBrowser,
  selections: Readonly<{ selectedOrganization: string | undefined; selectedTemplateName: string | undefined }>
): AAPSelectionStaleness {
  const { isActive, error, loadingOrgs, loadingTemplates, organizations, templates } = browser

  if (!isActive || error || loadingOrgs || loadingTemplates) {
    return { organization: false, template: false }
  }

  const organizationStale =
    !!selections.selectedOrganization && !organizations.some((org) => org.name === selections.selectedOrganization)

  const templateStale =
    !!selections.selectedTemplateName &&
    !templates.some((template) => template.name === selections.selectedTemplateName)

  return {
    organization: organizationStale,
    // The template flag is meaningless once the organization cascade clears it
    template: !organizationStale && templateStale,
  }
}
