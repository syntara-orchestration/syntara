import { RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { toFeatureFlagKey } from '../utils/feature-flags'

import App from './App'

// Stub out the real TanStack router instance (avoids building the full route tree).
vi.mock('./tanstackRouter', () => ({ tanstackRouter: {} }))

// Override RouterProvider so we can control rendering per-test without building
// a real router. Default behavior (vi.fn with no implementation) renders nothing;
// individual tests call mockReturnValue/mockImplementation as needed.
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, RouterProvider: vi.fn() }
})

// Mock auth store so AppLogin immediately renders its children
vi.mock('../stores/useAuthStore', () => ({
  useAuthStore: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({
        isAuthenticated: true,
        isRefreshing: false,
        error: null,
        login: vi.fn(),
        refresh: vi.fn(),
        logout: vi.fn(),
      }),
    { setState: vi.fn(), getState: vi.fn(() => ({})) }
  ),
  selectIsAuthenticated: (state: { isAuthenticated: boolean }) => state.isAuthenticated,
  selectIsRefreshing: (state: { isRefreshing: boolean }) => state.isRefreshing,
}))

// Mock useAuthProviders to prevent async fetch + state updates
vi.mock('./useAuthProviders', () => ({
  useAuthProviders: () => ({ providers: [], isLoading: false }),
}))

describe('App', () => {
  afterEach(() => {
    globalThis.localStorage.removeItem(toFeatureFlagKey('workflow_builder_qol'))
    vi.clearAllMocks()
  })

  it('renders without crashing', () => {
    vi.mocked(RouterProvider).mockReturnValue(null as never)
    render(<App />)
    expect(document.body).toBeInTheDocument()
  })

  it('passes the app router and feature flag snapshot to RouterProvider', () => {
    globalThis.localStorage.setItem(toFeatureFlagKey('workflow_builder_qol'), 'true')
    vi.mocked(RouterProvider).mockReturnValue(null as never)
    render(<App />)
    expect(vi.mocked(RouterProvider).mock.lastCall?.[0]).toHaveProperty('router')
    expect(vi.mocked(RouterProvider).mock.lastCall?.[0]).toHaveProperty(
      'context.featureFlags.workflow_builder_qol',
      true
    )
  })

  it('renders the main application structure', async () => {
    vi.mocked(RouterProvider).mockImplementation(() => (
      <>
        <header role="banner">
          <nav aria-label="Main navigation" />
        </header>
        <div role="main" />
      </>
    ))
    render(<App />)
    expect(await screen.findByRole('banner')).toBeInTheDocument()
  })

  it('renders navigation dock', async () => {
    vi.mocked(RouterProvider).mockImplementation(() => <nav aria-label="Main navigation" />)
    render(<App />)
    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
  })

  it('renders main landmark region', async () => {
    vi.mocked(RouterProvider).mockImplementation(() => <div role="main" />)
    render(<App />)
    expect(await screen.findByRole('main')).toBeInTheDocument()
  })
})
