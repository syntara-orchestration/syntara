import {
  Button,
  CompassDockMain,
  Divider,
  Dropdown,
  DropdownItem,
  DropdownList,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadLogo,
  MastheadMain,
  MastheadToggle,
  Menu,
  MenuItem,
  MenuList,
  MenuToggle,
  Nav,
  NavContext,
  NavExpandable,
  NavItem,
  NavList,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
  Tooltip,
} from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import {
  RhUiDarkModeIcon,
  RhUiLightModeIcon,
  RhUiProfileFillIcon,
  RhUiQuestionMarkCircleIcon,
} from '@patternfly/react-icons'
import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { use, useMemo, useRef, useState } from 'react'

import { authClient } from '../client'
import { useAlerts } from '../providers/alerts'
import { useBrand } from '../providers/brand'
import { useColorScheme } from '../providers/theme/useColorScheme'
import { useAuthStore } from '../stores/useAuthStore'
import { getErrorMessage } from '../utils/apiErrors'
import { detachPromise } from '../utils/detachPromise'
import { useDocLink } from '../utils/docs/useDocLink'

import styles from './AppDockedNav.module.css'
import { AppRoute } from './AppRoute'
import type { TNavigationItem } from './navigationItems'
import { useDockState } from './useDockState'
import { useFilteredNavigationItems } from './useFilteredNavigationItems'
import { useUnsavedChanges } from './useUnsavedChanges'

function findFirstEnabledPath(item: TNavigationItem): string {
  if (item.children?.length) {
    return item.children[0].path
  }
  return item.path
}

/** Items with children that should show a dropdown instead of navigating directly. */
function hasDropdownChildren(item: TNavigationItem): boolean {
  return (item.children?.length ?? 0) > 1
}

function createNavItemRefs(items: TNavigationItem[]) {
  const refs: Record<string, React.RefObject<HTMLAnchorElement | null>> = {}
  items.forEach((item) => {
    refs[item.path] = { current: null }
  })
  return refs
}

function navigateToNavItem(
  itemId: string | number,
  visibleItems: TNavigationItem[],
  requestNavigation: (path: string) => void
) {
  const item = visibleItems.find((navItem) => navItem.path === itemId)
  if (item) requestNavigation(findFirstEnabledPath(item))
}

function openExternalDoc(url: string) {
  globalThis.open(url, '_blank', 'noopener,noreferrer')
}

function NavDropdownItem({
  item,
  isActive,
  requestNavigation,
}: Readonly<{
  item: TNavigationItem
  isActive: boolean
  requestNavigation: (path: string) => void
}>) {
  const enabledChildren = item.children ?? []
  const { setFlyoutRef } = use(NavContext)

  const onMenuSelect = (_event: React.MouseEvent | undefined, itemId: string | number | undefined) => {
    const child = enabledChildren.find((c) => c.path === itemId)
    if (child) {
      setFlyoutRef?.(null)
      requestNavigation(child.path)
    }
  }

  /* v8 ignore start -- phantom branches from compiled JSX props and map callback */
  return (
    <NavItem
      preventDefault
      isActive={isActive}
      icon={item.icon}
      aria-label={item.label}
      itemId={item.path}
      id={`nav-${item.path.replaceAll('/', '-')}`}
      className={styles.navFlyoutItem}
      flyout={
        <Menu containsFlyout isNavFlyout onSelect={onMenuSelect} className={styles.flyoutMenu}>
          <MenuList>
            {enabledChildren.map((child) => (
              <MenuItem
                key={child.path}
                icon={child.icon}
                itemId={child.path}
                className={styles.flyoutMenuItem}
                onClick={(e: React.MouseEvent) => e.preventDefault()}
              >
                {child.label}
              </MenuItem>
            ))}
          </MenuList>
        </Menu>
      }
    >
      {item.label}
    </NavItem>
  )
  /* v8 ignore stop */
}

function NavExpandableItem({
  item,
  isActive,
  location,
  requestNavigation,
}: Readonly<{
  item: TNavigationItem
  isActive: boolean
  location: string
  requestNavigation: (path: string) => void
}>) {
  const enabledChildren = item.children ?? []

  /* v8 ignore start -- phantom branches from compiled JSX props and map callback */
  return (
    <NavExpandable
      title={
        <>
          <span className={`pf-v6-c-nav__link-icon ${styles.navExpandableIcon}`} aria-hidden="true">
            {item.icon}
          </span>
          {item.label}
        </>
      }
      isActive={isActive}
      isExpanded
      id={`nav-${item.path.replaceAll('/', '-')}`}
    >
      {enabledChildren.map((child) => (
        <NavItem
          key={child.path}
          preventDefault
          id={`nav-${child.path.replaceAll('/', '-')}`}
          itemId={child.path}
          href={child.path}
          isActive={location.startsWith(child.path)}
          icon={child.icon}
          onClick={() => requestNavigation(child.path)}
        >
          {child.label}
        </NavItem>
      ))}
    </NavExpandable>
  )
  /* v8 ignore stop */
}

function UserMenuDropdown() {
  const [isOpen, setIsOpen] = useState(false)
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const { showAlert } = useAlerts()
  const { data: currentUser } = authClient.useQuery('get', '/auth/me')

  const handleLogoutClick = () => {
    setIsOpen(false)
    detachPromise(logout(), {
      onReject: (error: unknown) => {
        showAlert({
          title: 'Sign out failed',
          description: getErrorMessage(error),
          variant: 'danger',
          autoDismiss: false,
        })
      },
    })
  }

  /* v8 ignore start -- phantom branches from compiled JSX props */
  const toggle = (dropdownRef: React.Ref<MenuToggleElement>) => (
    <MenuToggle
      ref={dropdownRef}
      isExpanded={isOpen}
      variant="plain"
      icon={<RhUiProfileFillIcon />}
      isDocked
      className={styles.dockedAction}
      aria-label="User menu"
      onClick={() => setIsOpen(!isOpen)}
      onMouseEnter={() => setIsOpen(true)}
    >
      {currentUser?.username ?? 'User'}
    </MenuToggle>
  )

  return (
    <Dropdown
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      toggle={toggle}
      popperProps={{ position: 'right', preventOverflow: true }}
    >
      <DropdownList>
        <DropdownItem
          key="profile"
          onClick={() => {
            detachPromise(navigate({ to: AppRoute.MyProfile.Root }))
            setIsOpen(false)
          }}
        >
          My Profile
        </DropdownItem>
        <DropdownItem key="logout" onClick={handleLogoutClick}>
          Logout
        </DropdownItem>
      </DropdownList>
    </Dropdown>
  )
  /* v8 ignore stop */
}

export function AppDockedNav() {
  const location = useRouterState({ select: (s) => s.location.pathname })
  const { requestNavigation } = useUnsavedChanges()
  const { colorScheme, toggleColorScheme } = useColorScheme()
  const brand = useBrand()
  const docsHomeUrl = useDocLink('home')
  const { isDockExpanded, isDockTextExpanded, isMobile, dockedToggleRef, onToggleDock } = useDockState()

  const filteredItems = useFilteredNavigationItems()
  const visibleItems = useMemo(
    () => filteredItems.filter((item) => !item.hidden && !item.path.startsWith('/support')),
    [filteredItems]
  )
  const activeTopLevel = '/' + location.split('/')[1]

  const colorSchemeRef = useRef<HTMLButtonElement>(null)
  const helpRef = useRef<HTMLButtonElement>(null)
  const navItemRefs = useMemo(() => createNavItemRefs(visibleItems), [visibleItems])

  const colorSchemeToggleLabel = colorScheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
  const isExpanded = isDockTextExpanded || isDockExpanded
  const showTooltips = !isExpanded

  /* v8 ignore start -- phantom branches from compiled JSX props, ternaries, and map callbacks */
  return (
    <CompassDockMain {...(isMobile && !isDockExpanded && { inert: true })}>
      <Masthead id="docked-masthead" variant="docked" className={styles.dockedMasthead}>
        <MastheadMain>
          <MastheadToggle>
            <Button
              ref={dockedToggleRef}
              variant="plain"
              isHamburger
              onClick={onToggleDock}
              aria-label="Global navigation"
              isExpanded={isDockTextExpanded}
            />
          </MastheadToggle>
          <MastheadBrand className={!isExpanded ? styles.collapsedBrand : undefined}>
            {isExpanded ? (
              <MastheadLogo component={(props) => <Link {...props} to="/" />} aria-label="Home">
                <img
                  src={colorScheme === 'dark' ? brand.logoExpandedDark : brand.logoExpandedLight}
                  alt={brand.appTitle}
                  className={styles.expandedLogo}
                  data-testid="brand-logo"
                />
              </MastheadLogo>
            ) : (
              <MastheadLogo
                component={(props) => <Link {...props} to="/" />}
                aria-label="Home"
                className={`pf-m-compact ${styles.compactLogo}`}
              >
                <img
                  src={brand.logoCollapsed}
                  alt={brand.appTitle}
                  className={styles.collapsedLogo}
                  data-testid="brand-logo"
                />
              </MastheadLogo>
            )}
          </MastheadBrand>
        </MastheadMain>
        <Divider />
        <MastheadContent>
          <Toolbar id="docked-toolbar" isVertical>
            <ToolbarContent>
              <ToolbarItem>
                <Nav
                  onSelect={(_event, selectedItem) =>
                    navigateToNavItem(selectedItem.itemId, visibleItems, requestNavigation)
                  }
                  variant="docked"
                  aria-label="Main navigation"
                  className={!isDockTextExpanded ? styles.iconDockNav : undefined}
                >
                  <NavList>
                    {visibleItems.flatMap((item) => {
                      const itemTopLevel = '/' + item.path.split('/')[1]
                      const isActive = itemTopLevel === activeTopLevel
                      const separator = item.separatorBefore ? (
                        <Divider key={`divider-${item.path}`} component="li" />
                      ) : null
                      if (hasDropdownChildren(item)) {
                        return [
                          separator,
                          isExpanded ? (
                            <NavExpandableItem
                              key={item.path}
                              item={item}
                              isActive={isActive}
                              location={location}
                              requestNavigation={requestNavigation}
                            />
                          ) : (
                            <NavDropdownItem
                              key={item.path}
                              item={item}
                              isActive={isActive}
                              requestNavigation={requestNavigation}
                            />
                          ),
                        ]
                      }
                      return [
                        separator,
                        <NavItem
                          key={item.path}
                          preventDefault
                          id={`nav-${item.path.replaceAll('/', '-')}`}
                          itemId={item.path}
                          href={findFirstEnabledPath(item)}
                          isActive={isActive}
                          icon={item.icon}
                          aria-label={item.label}
                          anchorRef={navItemRefs[item.path]}
                        >
                          {item.label}
                        </NavItem>,
                      ]
                    })}
                  </NavList>
                </Nav>
                {showTooltips &&
                  visibleItems
                    .filter((item) => !hasDropdownChildren(item))
                    .map((item) => (
                      <Tooltip
                        key={`tooltip-${item.path}`}
                        aria="none"
                        aria-live="off"
                        triggerRef={navItemRefs[item.path]}
                        content={item.label}
                        position="right"
                      />
                    ))}
              </ToolbarItem>
              <ToolbarGroup
                variant="action-group-plain"
                align={{ default: 'alignEnd' }}
                gap={{ default: 'gapNone', md: 'gapMd' }}
              >
                <ToolbarItem>
                  <Button
                    variant="plain"
                    isDocked
                    className={styles.dockedAction}
                    icon={colorScheme === 'dark' ? <RhUiDarkModeIcon /> : <RhUiLightModeIcon />}
                    aria-label={colorSchemeToggleLabel}
                    ref={colorSchemeRef}
                    onClick={toggleColorScheme}
                  >
                    {colorScheme === 'dark' ? 'Light mode' : 'Dark mode'}
                  </Button>
                </ToolbarItem>
                <ToolbarItem>
                  <Button
                    variant="plain"
                    isDocked
                    className={styles.dockedAction}
                    icon={<RhUiQuestionMarkCircleIcon />}
                    aria-label="Documentation (opens in a new tab)"
                    ref={helpRef}
                    onClick={() => openExternalDoc(docsHomeUrl)}
                  >
                    Documentation
                  </Button>
                </ToolbarItem>
                <ToolbarItem>
                  <UserMenuDropdown />
                </ToolbarItem>
              </ToolbarGroup>
            </ToolbarContent>
          </Toolbar>
        </MastheadContent>
        {showTooltips && (
          <>
            <Tooltip
              aria="none"
              aria-live="off"
              triggerRef={colorSchemeRef}
              content={colorSchemeToggleLabel}
              position="right"
            />
            <Tooltip aria="none" aria-live="off" triggerRef={helpRef} content="Documentation" position="right" />
          </>
        )}
      </Masthead>
    </CompassDockMain>
  )
  /* v8 ignore stop */
}
