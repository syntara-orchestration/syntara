import {
  Brand,
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
  MenuToggle,
  Nav,
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
import { RhUiProfileFillIcon, RhUiQuestionMarkCircleIcon } from '@patternfly/react-icons'
// eslint-disable-next-line @typescript-eslint/no-restricted-imports -- MastheadLogo needs a plain anchor; SynLink adds PF Button styling
import { Link, useNavigate, useRouter, useRouterState } from '@tanstack/react-router'
import { useMemo, useRef, useState } from 'react'

import { authClient } from '../client'
import { useAlerts } from '../providers/alerts'
import { useBrand } from '../providers/brand'
import { useColorScheme } from '../providers/theme/useColorScheme'
import { useAuthStore } from '../stores/useAuthStore'
import { getErrorMessage } from '../utils/apiErrors'
import { detachPromise } from '../utils/detachPromise'
import { useDocLink } from '../utils/docs/useDocLink'

import type { TNavigationItem } from './navigationItems'
import type { AppRouteNavigationOptions } from './routeNavigationOptions'
import * as routeRefs from './routes/routeReferences'
import { ThemeMenu } from './ThemeMenu'
import { useDockState } from './useDockState'
import { useFilteredNavigationItems } from './useFilteredNavigationItems'
import { useUnsavedChanges } from './useUnsavedChanges'

function MastheadHomeLink(props: React.ComponentProps<typeof Link>) {
  return <Link {...props} to="/" />
}

function navigationItemId(item: TNavigationItem): string {
  return item.id ?? item.matchPath ?? item.destination?.to ?? item.label
}

function findFirstEnabledDestination(item: TNavigationItem): AppRouteNavigationOptions {
  const childDestination = item.children?.find((child) => !child.hidden && child.destination)?.destination
  const destination = childDestination ?? item.destination
  if (!destination) throw new Error(`Navigation item has no route destination: ${item.label}`)
  return destination
}

/** Items with multiple children render as expandable groups instead of direct links. */
function hasDropdownChildren(item: TNavigationItem): boolean {
  return (item.children?.length ?? 0) > 1
}

function createNavItemRefs(items: TNavigationItem[]) {
  const refs: Record<string, React.RefObject<HTMLAnchorElement | null>> = {}
  items.forEach((item) => {
    refs[navigationItemId(item)] = { current: null }
  })
  return refs
}

function createExpandableRefs(items: TNavigationItem[]) {
  const refs: Record<string, React.RefObject<HTMLButtonElement | null>> = {}
  items.forEach((item) => {
    if (hasDropdownChildren(item)) {
      refs[navigationItemId(item)] = { current: null }
    }
  })
  return refs
}

function navigateToNavItem(
  itemId: string | number,
  visibleItems: TNavigationItem[],
  requestNavigation: (destination: AppRouteNavigationOptions) => void
) {
  const item = visibleItems.find((navItem) => navigationItemId(navItem) === itemId)
  if (item) requestNavigation(findFirstEnabledDestination(item))
}

function openExternalDoc(url: string) {
  globalThis.open(url, '_blank', 'noopener,noreferrer')
}

function getNavGroupId(itemId: string): string {
  return `nav-expandable-${itemId.replaceAll('/', '-')}`
}

function NavExpandableItem({
  item,
  isActive,
  isExpanded,
  isMobile,
  buttonRef,
  location,
  onExpand,
  requestNavigation,
  router,
}: Readonly<{
  item: TNavigationItem
  isActive: boolean
  isExpanded: boolean
  isMobile: boolean
  buttonRef?: React.RefObject<HTMLButtonElement | null>
  location: string
  onExpand: (event: React.MouseEvent<HTMLButtonElement>, isExpanded: boolean) => void
  requestNavigation: (destination: AppRouteNavigationOptions) => void
  router: ReturnType<typeof useRouter>
}>) {
  const enabledChildren =
    item.children?.flatMap((child) =>
      !child.hidden && child.destination ? [{ item: child, destination: child.destination }] : []
    ) ?? []
  const itemId = navigationItemId(item)
  const groupId = getNavGroupId(itemId)

  /* v8 ignore start -- phantom branches from compiled JSX props and map callback */
  return (
    <NavExpandable
      title={item.label}
      icon={item.icon}
      groupId={groupId}
      hasExpandableIcon={!isMobile}
      isExpanded={isExpanded}
      isActive={isActive}
      id={`nav-${itemId.replaceAll('/', '-')}`}
      buttonProps={{
        'aria-label': item.label,
        ...(buttonRef ? { ref: buttonRef } : {}),
      }}
      aria-label={item.label}
      onExpand={onExpand}
    >
      {enabledChildren.map(({ item: child, destination }) => (
        <NavItem
          key={navigationItemId(child)}
          preventDefault
          id={`nav-${navigationItemId(child).replaceAll('/', '-')}`}
          groupId={groupId}
          itemId={navigationItemId(child)}
          href={router.buildLocation(destination).href}
          isActive={location.startsWith(child.matchPath ?? destination.to)}
          icon={child.icon}
          onClick={() => requestNavigation(destination)}
        >
          {child.label}
        </NavItem>
      ))}
    </NavExpandable>
  )
  /* v8 ignore stop */
}

function UserMenuDropdown({ showTooltip }: Readonly<{ showTooltip: boolean }>) {
  const [isOpen, setIsOpen] = useState(false)
  const userMenuRef = useRef<MenuToggleElement>(null)
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const { showAlert } = useAlerts()
  const { data: currentUser } = authClient.useQuery('get', '/auth/me')
  const username = currentUser?.username ?? 'User'

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
      ref={(element) => {
        userMenuRef.current = element
        if (typeof dropdownRef === 'function') {
          dropdownRef(element)
        } else if (dropdownRef) {
          dropdownRef.current = element
        }
      }}
      isExpanded={isOpen}
      variant="plain"
      icon={<RhUiProfileFillIcon />}
      isDocked
      aria-label="User menu"
      onClick={() => setIsOpen(!isOpen)}
    >
      {username}
    </MenuToggle>
  )

  return (
    <>
      <Dropdown
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        toggle={toggle}
        popperProps={{ placement: 'right-start', preventOverflow: true, enableFlip: false }}
      >
        <DropdownList>
          <DropdownItem
            key="profile"
            onClick={() => {
              detachPromise(navigate({ to: routeRefs.myProfileRootRoute.fullPath }))
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
      {showTooltip && !isOpen && (
        <Tooltip aria="none" aria-live="off" triggerRef={userMenuRef} content="Account" position="right" />
      )}
    </>
  )
  /* v8 ignore stop */
}

export function AppDockedNav() {
  const location = useRouterState({ select: (s) => s.location.pathname })
  const router = useRouter()
  const { requestNavigation } = useUnsavedChanges()
  const requestRouteNavigation = (destination: AppRouteNavigationOptions) => requestNavigation(destination)
  const { colorScheme } = useColorScheme()
  const brand = useBrand()
  const docsHomeUrl = useDocLink('home')
  const { isDockExpanded, isMobile, dockedToggleRef, onToggleDock, isNavGroupExpanded, onExpandNavGroup, onNavSelect } =
    useDockState()

  const filteredItems = useFilteredNavigationItems()
  const visibleItems = useMemo(() => filteredItems.filter((item) => !item.hidden), [filteredItems])
  const activeTopLevel = '/' + location.split('/')[1]

  const helpRef = useRef<HTMLButtonElement>(null)
  const navItemRefs = useMemo(() => createNavItemRefs(visibleItems), [visibleItems])
  const expandableRefs = useMemo(() => createExpandableRefs(visibleItems), [visibleItems])

  const showTooltips = !isDockExpanded

  /* v8 ignore start -- phantom branches from compiled JSX props, ternaries, and map callbacks */
  return (
    <CompassDockMain {...(isMobile && !isDockExpanded && { inert: true })}>
      <Masthead display={{ default: undefined }} id="docked-masthead" variant="docked">
        <MastheadMain>
          <MastheadToggle>
            <Button
              ref={dockedToggleRef}
              variant="plain"
              isHamburger
              onClick={onToggleDock}
              aria-label="Global navigation"
              isExpanded={isDockExpanded}
            />
          </MastheadToggle>
          <MastheadBrand>
            <MastheadLogo component={MastheadHomeLink} aria-label="Home" isCompact>
              <Brand src={brand.logoCollapsed} alt={brand.appTitle} data-testid="brand-logo" />
            </MastheadLogo>
            <MastheadLogo component={MastheadHomeLink} aria-label="Home">
              <Brand
                src={colorScheme === 'dark' ? brand.logoExpandedDark : brand.logoExpandedLight}
                alt={brand.appTitle}
                data-testid="brand-logo"
              />
            </MastheadLogo>
          </MastheadBrand>
        </MastheadMain>
        <Divider />
        <MastheadContent>
          <Toolbar id="docked-toolbar" isVertical>
            <ToolbarContent>
              <ToolbarItem>
                <Nav
                  onSelect={(_event, selectedItem) => {
                    navigateToNavItem(selectedItem.itemId, visibleItems, requestRouteNavigation)
                    onNavSelect()
                  }}
                  variant="docked"
                  aria-label="Main navigation"
                >
                  <NavList>
                    {visibleItems.flatMap((item) => {
                      const itemId = navigationItemId(item)
                      const itemPath = item.matchPrefix ?? item.matchPath ?? item.destination?.to ?? ''
                      const itemTopLevel = '/' + itemPath.split('/')[1]
                      const isActive = itemTopLevel === activeTopLevel
                      const separator = item.separatorBefore ? (
                        <Divider key={`divider-${itemId}`} component="li" />
                      ) : null
                      if (hasDropdownChildren(item)) {
                        return [
                          separator,
                          <NavExpandableItem
                            key={itemId}
                            item={item}
                            isActive={isActive}
                            isExpanded={isNavGroupExpanded(getNavGroupId(itemId))}
                            isMobile={isMobile}
                            buttonRef={expandableRefs[itemId]}
                            location={location}
                            onExpand={(event, expanded) => onExpandNavGroup(event, getNavGroupId(itemId), expanded)}
                            requestNavigation={requestRouteNavigation}
                            router={router}
                          />,
                        ]
                      }
                      const destination = findFirstEnabledDestination(item)
                      return [
                        separator,
                        <NavItem
                          key={itemId}
                          preventDefault
                          id={`nav-${itemId.replaceAll('/', '-')}`}
                          itemId={itemId}
                          href={router.buildLocation(destination).href}
                          isActive={isActive}
                          icon={item.icon}
                          aria-label={item.label}
                          anchorRef={navItemRefs[itemId]}
                        >
                          {item.label}
                        </NavItem>,
                      ]
                    })}
                  </NavList>
                </Nav>
                {showTooltips &&
                  visibleItems.map((item) => (
                    <Tooltip
                      key={`tooltip-${navigationItemId(item)}`}
                      aria="none"
                      aria-live="off"
                      triggerRef={expandableRefs[navigationItemId(item)] ?? navItemRefs[navigationItemId(item)]}
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
                  <ThemeMenu showTooltip={showTooltips} />
                </ToolbarItem>
                <ToolbarItem>
                  <Button
                    variant="plain"
                    isDocked
                    icon={<RhUiQuestionMarkCircleIcon />}
                    aria-label="Documentation (opens in a new tab)"
                    ref={helpRef}
                    onClick={() => openExternalDoc(docsHomeUrl)}
                  >
                    Documentation
                  </Button>
                </ToolbarItem>
                <ToolbarItem>
                  <UserMenuDropdown showTooltip={showTooltips} />
                </ToolbarItem>
              </ToolbarGroup>
            </ToolbarContent>
          </Toolbar>
        </MastheadContent>
        {showTooltips && (
          <Tooltip aria="none" aria-live="off" triggerRef={helpRef} content="Documentation" position="right" />
        )}
      </Masthead>
    </CompassDockMain>
  )
  /* v8 ignore stop */
}
