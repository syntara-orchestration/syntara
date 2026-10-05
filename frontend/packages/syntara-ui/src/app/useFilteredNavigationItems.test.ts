import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { usePermissionChecks as UsePermissionChecksFn } from '../hooks/usePermissionChecks'

import { useFilteredNavigationItems } from './useFilteredNavigationItems'

const mockUsePermissionChecks = vi.fn<typeof UsePermissionChecksFn>()

vi.mock('../hooks/usePermissionChecks', () => ({
  usePermissionChecks: (...args: Parameters<typeof UsePermissionChecksFn>) => mockUsePermissionChecks(...args),
}))

vi.mock('../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../routes/access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
    use: vi.fn(),
  },
}))

/** Helper: find a nav item by label at any depth */
function findItem(
  items: readonly { label: string; children?: readonly { label: string }[] }[],
  label: string
): { label: string } | undefined {
  for (const item of items) {
    if (item.label === label) return item
    if (item.children) {
      // eslint-disable-next-line testing-library/no-node-access -- .children is a TNavigationItem property, not DOM node access
      const found = findItem(item.children, label)
      if (found) return found
    }
  }
  return undefined
}

/** All permission keys used by nav items — defaults to all granted */
function setPermissions(overrides: Record<string, boolean>) {
  mockUsePermissionChecks.mockReturnValue({
    permissions: {
      'setting:read': true,
      'user:read': true,
      'group:read': true,
      'identity-provider:read': true,
      'project:read': true,
      'role-assignment:read': true,
      'role-assignment:assign': true,
      'service_account:read': true,
      'approval:read': true,
      ...overrides,
    },
    isLoading: false,
  })
}

describe('useFilteredNavigationItems', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setPermissions({})
  })

  it('requests nav permissions with checkAnyProject', () => {
    renderHook(() => useFilteredNavigationItems())
    expect(mockUsePermissionChecks).toHaveBeenCalledWith(expect.any(Array), { checkAnyProject: true })
  })

  it('includes all gated items when all permissions are allowed', () => {
    setPermissions({})
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Settings')).toBeDefined()
    expect(findItem(result.current, 'Users')).toBeDefined()
    expect(findItem(result.current, 'Groups')).toBeDefined()
    expect(findItem(result.current, 'Identity Providers')).toBeDefined()
    expect(findItem(result.current, 'Access Management')).toBeDefined()
  })

  it('excludes Settings when setting:read is denied', () => {
    setPermissions({ 'setting:read': false })
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Settings')).toBeUndefined()
    expect(findItem(result.current, 'Users')).toBeDefined()
    expect(findItem(result.current, 'Groups')).toBeDefined()
  })

  it('always includes items without requiredPermissions', () => {
    setPermissions({
      'setting:read': false,
      'user:read': false,
      'group:read': false,
      'identity-provider:read': false,
      'project:read': false,
      'role-assignment:read': false,
      'role-assignment:assign': false,
      'approval:read': true, // Tasks nav requires approval or form_prompt permissions
    })
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Workflows')).toBeDefined()
    expect(findItem(result.current, 'Tasks')).toBeDefined()
    expect(findItem(result.current, 'Workflow Runs')).toBeDefined()
  })

  it('excludes Tasks when approval and form_prompt read are denied', () => {
    setPermissions({ 'approval:read': false })
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Tasks')).toBeUndefined()
    expect(findItem(result.current, 'Workflows')).toBeDefined()
    expect(findItem(result.current, 'Workflow Runs')).toBeDefined()
  })

  it('excludes Identity Providers when identity-provider:read is denied', () => {
    setPermissions({ 'identity-provider:read': false })
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Identity Providers')).toBeUndefined()
    expect(findItem(result.current, 'Settings')).toBeDefined()
  })

  it('preserves other System Administration children when Settings is filtered', () => {
    setPermissions({ 'setting:read': false })
    const { result } = renderHook(() => useFilteredNavigationItems())

    expect(findItem(result.current, 'Access Management')).toBeDefined()
    expect(findItem(result.current, 'Identity Providers')).toBeDefined()
    expect(findItem(result.current, 'Settings')).toBeUndefined()
  })

  describe('Access Management section-level gating', () => {
    it('shows Access Management when role-assignment:read is granted', () => {
      setPermissions({
        'user:read': false,
        'group:read': false,
        'project:read': false,
        'role-assignment:read': true,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Access Management')).toBeDefined()
    })

    it('does not show Access Management for project:read alone', () => {
      setPermissions({
        'user:read': false,
        'group:read': false,
        'project:read': true,
        'role-assignment:read': false,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Access Management')).toBeUndefined()
    })

    it('hides Access Management when all AM permissions are denied', () => {
      setPermissions({
        'user:read': false,
        'group:read': false,
        'project:read': false,
        'role-assignment:read': false,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Access Management')).toBeUndefined()
    })
  })

  describe('Access Management tab gating', () => {
    it('filters out Users tab when user:read is denied', () => {
      setPermissions({ 'user:read': false })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Users')).toBeUndefined()
      expect(findItem(result.current, 'Groups')).toBeDefined()
    })

    it('filters out Groups tab when group:read is denied', () => {
      setPermissions({ 'group:read': false })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Users')).toBeDefined()
      expect(findItem(result.current, 'Groups')).toBeUndefined()
    })

    it('filters out both Users and Groups when both are denied', () => {
      setPermissions({ 'user:read': false, 'group:read': false })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Users')).toBeUndefined()
      expect(findItem(result.current, 'Groups')).toBeUndefined()
    })
  })

  describe('section-level hiding', () => {
    it('hides System Administration when all children are denied', () => {
      setPermissions({
        'setting:read': false,
        'identity-provider:read': false,
        'user:read': false,
        'group:read': false,
        'project:read': false,
        'role-assignment:read': false,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'System Administration')).toBeUndefined()
    })

    it('keeps System Administration when at least one child is visible', () => {
      setPermissions({
        'setting:read': true,
        'identity-provider:read': false,
        'user:read': false,
        'group:read': false,
        'project:read': false,
        'role-assignment:read': false,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'System Administration')).toBeDefined()
      expect(findItem(result.current, 'Settings')).toBeDefined()
    })

    it('keeps Configuration visible when Credentials is ungated even if Integrations is denied', () => {
      setPermissions({
        'setting:read': false,
        'identity-provider:read': false,
        'user:read': false,
        'group:read': false,
        'project:read': false,
        'role-assignment:read': false,
        'role-assignment:assign': false,
        'integration:read': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Configuration')).toBeDefined()
      expect(findItem(result.current, 'Integrations')).toBeUndefined()
      expect(findItem(result.current, 'Credentials')).toBeDefined()
    })
  })

  describe('project-scoped permissions via check_any_project', () => {
    it('shows Tasks when approval:read is granted anywhere', () => {
      setPermissions({ 'approval:read': true, 'approval:decide': false })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Tasks')).toBeDefined()
    })

    it('shows Tasks when approval:decide is granted anywhere', () => {
      setPermissions({ 'approval:read': false, 'approval:decide': true })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Tasks')).toBeDefined()
    })

    it('still hides Tasks when user has no task-related permissions at any scope', () => {
      setPermissions({ 'approval:read': false, 'approval:decide': false })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Tasks')).toBeUndefined()
    })

    it('shows Access Management for project-admin via role-assignment:read anywhere', () => {
      setPermissions({
        'user:read': false,
        'group:read': false,
        'role-assignment:read': true,
        'role-assignment:assign': false,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Access Management')).toBeDefined()
    })

    it('hides Access Management when only non-admin-worthy permissions are granted', () => {
      setPermissions({
        'user:read': false,
        'group:read': false,
        'role-assignment:read': false,
        'role-assignment:assign': false,
        'project:read': true,
      })
      const { result } = renderHook(() => useFilteredNavigationItems())

      expect(findItem(result.current, 'Access Management')).toBeUndefined()
    })
  })
})
