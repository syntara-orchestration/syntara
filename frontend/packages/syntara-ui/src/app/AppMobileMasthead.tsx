import {
  Button,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadLogo,
  MastheadMain,
  MastheadToggle,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from '@patternfly/react-core'
import { Link } from '@tanstack/react-router'

import { CommandPaletteNavButton } from '../components/command-palette/CommandPaletteNavButton'
import { useBrand } from '../providers/brand'

import styles from './AppMobileMasthead.module.css'
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
          <Button
            ref={mobileToggleRef}
            variant="plain"
            aria-label="Global navigation"
            isHamburger
            isExpanded={isDockExpanded}
            onClick={onMobileToggle}
          />
        </MastheadToggle>
        <MastheadBrand>
          <MastheadLogo component={(props) => <Link {...props} to="/" />} aria-label="Home">
            <img
              src={brand.logoCollapsed}
              alt={brand.appTitle}
              className={styles.collapsedLogo}
              data-testid="brand-logo"
            />
          </MastheadLogo>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar isStatic id="mobile-toolbar">
          <ToolbarContent>
            <ToolbarGroup variant="action-group-plain" align={{ default: 'alignEnd' }}>
              <ToolbarItem>
                <CommandPaletteNavButton isDocked={false} />
              </ToolbarItem>
            </ToolbarGroup>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  )
  /* v8 ignore stop */
}
