import {
  Brand,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadLogo,
  MastheadMain,
  MastheadToggle,
  PageToggleButton,
  Toolbar,
  ToolbarContent,
} from '@patternfly/react-core'
import { Link } from '@tanstack/react-router'

import { useBrand } from '../providers/brand'

import { useDockState } from './useDockState'

/**
 * Horizontal masthead shown only on mobile viewports (hidden on desktop by PF).
 * Provides a hamburger toggle to open the docked nav overlay and the app logo.
 * Currently invisible in practice because the app enforces a 1200 px minimum
 * viewport, but the component keeps the Compass layout spec-compliant so mobile
 * support can be enabled by relaxing that constraint.
 */
export function AppMobileMasthead() {
  const { isDockExpanded, onMobileToggle, mobileToggleRef } = useDockState()
  const brand = useBrand()

  /* v8 ignore start -- phantom branches from compiled JSX props */
  return (
    <Masthead display={{ default: 'inline' }} id="mobile-masthead">
      <MastheadMain>
        <MastheadToggle>
          <PageToggleButton
            innerRef={mobileToggleRef}
            id="mobile-masthead-toggle"
            variant="plain"
            aria-label="Global navigation"
            isHamburgerButton
            isSidebarOpen={isDockExpanded}
            onSidebarToggle={onMobileToggle}
          />
        </MastheadToggle>
        <MastheadBrand>
          <MastheadLogo component={(props) => <Link {...props} to="/" />} aria-label="Home">
            <Brand
              src={brand.logoCollapsed}
              alt={brand.appTitle}
              heights={{ default: '37px' }}
              data-testid="brand-logo"
            />
          </MastheadLogo>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar isStatic id="mobile-toolbar">
          <ToolbarContent />
        </Toolbar>
      </MastheadContent>
    </Masthead>
  )
  /* v8 ignore stop */
}
