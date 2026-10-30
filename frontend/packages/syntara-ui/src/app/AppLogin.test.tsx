import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../providers/alerts'
import { BrandProvider } from '../providers/brand'
import { ColorSchemeContext, type ColorSchemeContextValue } from '../providers/theme/colorSchemeReactContext'
import { AuthError } from '../stores/useAuthStore'

import { AppLogin } from './AppLogin'
import type { AuthProvider } from './useAuthProviders'

// Mock the auth store
const mockLogin = vi.fn()
const mockRefresh = vi.fn()
let mockState = {
  isAuthenticated: false,
  isRefreshing: false,
  error: null as string | null,
  logoutCount: 0,
  login: mockLogin,
  refresh: mockRefresh,
}

vi.mock('../stores/useAuthStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../stores/useAuthStore')>()
  return {
    AuthError: actual.AuthError,
    useAuthStore: Object.assign((selector: (state: typeof mockState) => unknown) => selector(mockState), {
      setState: vi.fn(),
      getState: () => mockState,
    }),
    selectIsAuthenticated: (state: typeof mockState) => state.isAuthenticated,
    selectIsRefreshing: (state: typeof mockState) => state.isRefreshing,
  }
})

// Mock useAuthProviders
let mockProviders: AuthProvider[] = []
let mockProvidersLoading = false

vi.mock('./useAuthProviders', () => ({
  useAuthProviders: () => ({
    providers: mockProviders,
    isLoading: mockProvidersLoading,
  }),
}))

function renderWithAlerts(ui: React.ReactNode, colorScheme: ColorSchemeContextValue['colorScheme'] = 'light') {
  const schemeCtx: ColorSchemeContextValue = {
    colorScheme,
    colorSchemePreference: colorScheme,
    setColorScheme: vi.fn(),
    toggleColorScheme: vi.fn(),
    contrastMode: 'glass',
    contrastPreference: 'system',
    setContrastMode: vi.fn(),
  }
  return render(
    <BrandProvider>
      <ColorSchemeContext value={schemeCtx}>
        <AlertProvider>{ui}</AlertProvider>
      </ColorSchemeContext>
    </BrandProvider>
  )
}

describe('AppLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockState = {
      isAuthenticated: false,
      isRefreshing: false,
      error: null,
      logoutCount: 0,
      login: mockLogin,
      refresh: mockRefresh,
    }
    // Default: refresh fails (no cookie), so login screen shows
    mockRefresh.mockRejectedValue(new Error('No cookie'))
    // Default: no providers
    mockProviders = []
    mockProvidersLoading = false
  })

  it('renders children when authenticated', () => {
    mockState.isAuthenticated = true

    renderWithAlerts(
      <AppLogin>
        <div data-testid="app-content">App Content</div>
      </AppLogin>
    )

    expect(screen.getByTestId('app-content')).toBeInTheDocument()
    expect(screen.getByText('App Content')).toBeInTheDocument()
  })

  it('shows loading state while refreshing', async () => {
    mockState.isRefreshing = true
    // refresh() never settles so the component stays in loading state
    mockRefresh.mockReturnValue(new Promise(() => {}))

    renderWithAlerts(
      <AppLogin>
        <div>Protected Content</div>
      </AppLogin>
    )

    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()

    // Flush the async bootstrap effect
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  })

  it('shows login button after bootstrap refresh fails', async () => {
    renderWithAlerts(
      <AppLogin>
        <div>Protected Content</div>
      </AppLogin>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    })

    expect(screen.getByText('Enter your credentials to continue')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('sets autocomplete="current-password" on the password field', async () => {
    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    const passwordInput = await screen.findByLabelText(/^Password/, { selector: 'input' })
    expect(passwordInput).toHaveAttribute('autocomplete', 'current-password')
  })

  it('calls login when login button is clicked', async () => {
    const user = userEvent.setup()
    // Login rejects so isLoggingIn resets and button reappears
    mockLogin.mockRejectedValueOnce(new Error('Login failed'))

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    // Wait for bootstrap to complete and login form to appear
    await screen.findByRole('button', { name: 'Log in' })

    // Fill in credentials (required by the LoginForm)
    await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
    await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'coffee')

    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({ username: 'demo', password: 'coffee' })
    })
  })

  it('attempts silent refresh on mount', async () => {
    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalledTimes(1)
    })
  })

  describe('session expired return URL', () => {
    afterEach(() => {
      sessionStorage.removeItem('ao_session_expired')
      sessionStorage.removeItem('ao_return_to')
    })

    it('restores previous location after successful refresh when session expired', async () => {
      mockRefresh.mockResolvedValue(undefined)
      sessionStorage.setItem('ao_session_expired', 'true')
      sessionStorage.setItem('ao_return_to', '/workflows/123')
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(replaceStateSpy).toHaveBeenCalledWith({}, '', '/workflows/123')
      })

      replaceStateSpy.mockRestore()
    })

    it('does not restore location when session expired flag is missing', async () => {
      mockRefresh.mockResolvedValue(undefined)
      sessionStorage.setItem('ao_return_to', '/workflows/123')
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(mockRefresh).toHaveBeenCalled()
      })
      expect(replaceStateSpy).not.toHaveBeenCalled()

      replaceStateSpy.mockRestore()
    })

    it('does not restore location when returnTo is root path', async () => {
      mockRefresh.mockResolvedValue(undefined)
      sessionStorage.setItem('ao_session_expired', 'true')
      sessionStorage.setItem('ao_return_to', '/')
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(mockRefresh).toHaveBeenCalled()
      })
      expect(replaceStateSpy).not.toHaveBeenCalled()

      replaceStateSpy.mockRestore()
    })

    it('does not restore location when returnTo contains protocol', async () => {
      mockRefresh.mockResolvedValue(undefined)
      sessionStorage.setItem('ao_session_expired', 'true')
      sessionStorage.setItem('ao_return_to', '/foo://bar')
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(mockRefresh).toHaveBeenCalled()
      })
      expect(replaceStateSpy).not.toHaveBeenCalled()

      replaceStateSpy.mockRestore()
    })

    it('clears session storage keys after consuming them', async () => {
      mockRefresh.mockResolvedValue(undefined)
      sessionStorage.setItem('ao_session_expired', 'true')
      sessionStorage.setItem('ao_return_to', '/workflows/123')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(mockRefresh).toHaveBeenCalled()
      })

      expect(sessionStorage.getItem('ao_session_expired')).toBeNull()
      expect(sessionStorage.getItem('ao_return_to')).toBeNull()
    })
  })

  it('does not call login automatically — only on button click', async () => {
    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    })

    expect(mockLogin).not.toHaveBeenCalled()
  })

  it('does not attempt auth when already authenticated', () => {
    mockState.isAuthenticated = true

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    expect(screen.getByText('Content')).toBeInTheDocument()
  })

  it('handles undefined children', () => {
    mockState.isAuthenticated = true

    const { container } = renderWithAlerts(<AppLogin />)

    expect(container).toBeInTheDocument()
  })

  it('handles null children', () => {
    mockState.isAuthenticated = true

    const { container } = renderWithAlerts(<AppLogin>{null}</AppLogin>)

    expect(container).toBeInTheDocument()
  })

  describe('with identity providers', () => {
    beforeEach(() => {
      mockProviders = [
        { id: 'okta-1', name: 'Okta', provider_type: 'oidc' },
        { id: 'azure-1', name: 'Azure AD', provider_type: 'oidc' },
      ]
    })

    it('shows loading state while providers are loading', async () => {
      // Arrange
      mockProvidersLoading = true
      // refresh() never settles so the component stays in loading state
      mockRefresh.mockReturnValue(new Promise(() => {}))

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Protected Content</div>
        </AppLogin>
      )

      // Assert
      expect(screen.getByLabelText('Loading')).toBeInTheDocument()
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()

      // Flush the async bootstrap effect
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0))
      })
    })

    it('renders IDP buttons when providers exist', async () => {
      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /log in with okta/i })).toBeInTheDocument()
      })
      expect(screen.getByRole('button', { name: /log in with azure ad/i })).toBeInTheDocument()
    })

    it('shows subtitle with identity provider instructions when providers exist', async () => {
      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByText(/Select your identity provider/)).toBeInTheDocument()
      })
    })

    it('does not show local login form by default when providers exist', async () => {
      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /log in with okta/i })).toBeInTheDocument()
      })
      expect(screen.queryByRole('textbox', { name: /username/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Log in' })).not.toBeInTheDocument()
    })

    it('shows "Sign in using local account" toggle button', async () => {
      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Sign in using local account' })).toBeInTheDocument()
      })
    })

    it('shows local login form when "Sign in using local account" is clicked', async () => {
      // Arrange
      const user = userEvent.setup()

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Wait for toggle button and click it
      const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(toggleButton)

      // Assert
      expect(screen.getByRole('textbox', { name: /username/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    })

    it('hides local login form when "Hide local account login" is clicked', async () => {
      // Arrange
      const user = userEvent.setup()

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Show local login
      const showButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(showButton)

      // Verify form is visible
      expect(screen.getByRole('textbox', { name: /username/i })).toBeInTheDocument()

      // Hide local login
      const hideButton = screen.getByRole('button', { name: 'Hide local account login' })
      await user.click(hideButton)

      // Assert - form is hidden
      await waitFor(() => {
        expect(screen.queryByRole('textbox', { name: /username/i })).not.toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: 'Log in' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Sign in using local account' })).toBeInTheDocument()
    })

    it('calls login when local login form is submitted', async () => {
      // Arrange
      const user = userEvent.setup()
      mockLogin.mockRejectedValueOnce(new Error('Login failed'))

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Show local login form
      const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(toggleButton)

      // Fill in credentials
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'admin')
      await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'password123')

      // Submit
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      // Assert
      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith({ username: 'admin', password: 'password123' })
      })
    })

    it('shows helper text for local account when form is visible', async () => {
      // Arrange
      const user = userEvent.setup()

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Show local login form
      const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(toggleButton)

      // Assert
      expect(
        screen.getByText('For local account access only. Other users should sign in using the identity provider above.')
      ).toBeInTheDocument()
    })

    it('keeps IDP buttons visible when local login is shown', async () => {
      // Arrange
      const user = userEvent.setup()

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Show local login form
      const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(toggleButton)

      // Assert - IDP buttons still visible
      expect(screen.getByRole('button', { name: /log in with okta/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /log in with azure ad/i })).toBeInTheDocument()
    })

    it('shows divider between IDP buttons and local login form', async () => {
      // Arrange
      const user = userEvent.setup()

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Show local login form
      const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
      await user.click(toggleButton)

      // Assert - divider is present
      expect(screen.getByRole('separator')).toBeInTheDocument()
    })
  })

  describe('without identity providers', () => {
    it('renders login form when no providers', async () => {
      // Arrange
      mockProviders = []

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Protected Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
      })

      expect(screen.getByText('Enter your credentials to continue')).toBeInTheDocument()
      expect(screen.queryByText(/Select your identity provider/)).not.toBeInTheDocument()
    })

    it('does not show IDP buttons when no providers', async () => {
      // Arrange
      mockProviders = []

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
      })

      expect(screen.queryByRole('button', { name: /log in with/i })).not.toBeInTheDocument()
    })

    it('does not show local account toggle when no providers', async () => {
      // Arrange
      mockProviders = []

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
      })

      expect(screen.queryByRole('button', { name: 'Sign in using local account' })).not.toBeInTheDocument()
    })

    it('shows username and password inputs immediately when no providers', async () => {
      // Arrange
      mockProviders = []

      // Act
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      // Assert
      await waitFor(() => {
        expect(screen.getByRole('textbox', { name: /username/i })).toBeInTheDocument()
      })
    })
  })

  describe('error handling', () => {
    it('shows inline error when submitting with empty username', async () => {
      const user = userEvent.setup()

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(screen.getByText('Enter your username')).toBeInTheDocument()
      })
      expect(mockLogin).not.toHaveBeenCalled()
    })

    it('shows inline error when submitting with empty password', async () => {
      const user = userEvent.setup()

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(screen.getByText('Enter your password')).toBeInTheDocument()
      })
      expect(mockLogin).not.toHaveBeenCalled()
    })

    it('clears password field on login failure', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValueOnce(new AuthError('Authentication required', 'AUTHENTICATION_REQUIRED'))

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      const passwordInput = screen.getByLabelText(/^Password/, { selector: 'input' })
      await user.type(passwordInput, 'wrongpassword')
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(passwordInput).toHaveValue('')
      })
    })

    it('maps AUTHENTICATION_REQUIRED to PF6 recommended message', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValueOnce(new AuthError('Authentication required', 'AUTHENTICATION_REQUIRED'))

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'wrong')
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(screen.getByText('Incorrect login credentials')).toBeInTheDocument()
      })
    })

    it('shows original message for non-auth errors', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValueOnce(new AuthError('Account locked', 'ACCOUNT_LOCKED'))

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'wrong')
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(screen.getByText('Account locked')).toBeInTheDocument()
      })
    })

    it('uses fallback error message for non-Error rejections', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValueOnce('network failure')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'wrong')
      await user.click(screen.getByRole('button', { name: 'Log in' }))

      await waitFor(() => {
        expect(screen.getByText('Incorrect login credentials')).toBeInTheDocument()
      })
    })

    it('clears error when user types in username field', async () => {
      const user = userEvent.setup()

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })

      // Trigger empty username error
      await user.click(screen.getByRole('button', { name: 'Log in' }))
      await waitFor(() => {
        expect(screen.getByText('Enter your username')).toBeInTheDocument()
      })

      // Type in username — error should clear
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'd')
      await waitFor(() => {
        expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
      })
    })

    it('clears error when user types in password field', async () => {
      const user = userEvent.setup()

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })

      // Fill username, trigger empty password error
      await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
      await user.click(screen.getByRole('button', { name: 'Log in' }))
      await waitFor(() => {
        expect(screen.getByText('Enter your password')).toBeInTheDocument()
      })

      // Type in password — error should clear
      await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'p')
      await waitFor(() => {
        expect(screen.queryByText('Enter your password')).not.toBeInTheDocument()
      })
    })

    it('login button is always clickable (not disabled for empty fields)', async () => {
      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      const loginButton = await screen.findByRole('button', { name: 'Log in' })
      expect(loginButton).not.toBeDisabled()
    })

    it('has no accessibility violations in error state', async () => {
      const user = userEvent.setup()

      const { container } = renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await screen.findByRole('button', { name: 'Log in' })

      // Trigger validation error
      await user.click(screen.getByRole('button', { name: 'Log in' }))
      await waitFor(() => {
        expect(screen.getByText('Enter your username')).toBeInTheDocument()
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    describe('with identity providers', () => {
      beforeEach(() => {
        mockProviders = [{ id: 'okta-1', name: 'Okta', provider_type: 'oidc' }]
      })

      it('does not show page-level alert for local login field validation errors', async () => {
        const user = userEvent.setup()

        renderWithAlerts(
          <AppLogin>
            <div>Content</div>
          </AppLogin>
        )

        const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
        await user.click(toggleButton)

        // Submit empty form — should show inline error, not the page-level Alert
        await user.click(screen.getByRole('button', { name: 'Log in' }))

        await waitFor(() => {
          expect(screen.getByText('Enter your username')).toBeInTheDocument()
        })
        expect(screen.queryByText('Authentication failed')).not.toBeInTheDocument()
      })

      it('shows page-level alert for local login auth failure in provider mode', async () => {
        const user = userEvent.setup()
        mockLogin.mockRejectedValueOnce(new AuthError('Authentication required', 'AUTHENTICATION_REQUIRED'))

        renderWithAlerts(
          <AppLogin>
            <div>Content</div>
          </AppLogin>
        )

        const toggleButton = await screen.findByRole('button', { name: 'Sign in using local account' })
        await user.click(toggleButton)

        await user.type(screen.getByRole('textbox', { name: /username/i }), 'admin')
        await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'wrong')
        await user.click(screen.getByRole('button', { name: 'Log in' }))

        // The page-level Alert title should render for credentials errors in provider mode
        await waitFor(() => {
          expect(screen.getByText('Authentication failed')).toBeInTheDocument()
        })
      })
    })
  })

  it('renders login page with dark color scheme', async () => {
    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>,
      'dark'
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    })

    expect(screen.getByRole('img')).toBeInTheDocument()
  })

  it('submits form via Enter key and prevents default', async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValueOnce(new Error('Login failed'))

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await screen.findByRole('button', { name: 'Log in' })

    await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
    await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'coffee{Enter}')

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({ username: 'demo', password: 'coffee' })
    })
  })

  it('uses fallback message when Error has empty message', async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValueOnce(new Error(''))

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await screen.findByRole('button', { name: 'Log in' })
    await user.type(screen.getByRole('textbox', { name: /username/i }), 'demo')
    await user.type(screen.getByLabelText(/^Password/, { selector: 'input' }), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => {
      expect(screen.getByText('Incorrect login credentials')).toBeInTheDocument()
    })
  })

  it('does not restore location when returnTo matches current pathname', async () => {
    mockRefresh.mockResolvedValue(undefined)
    sessionStorage.setItem('ao_session_expired', 'true')
    sessionStorage.setItem('ao_return_to', window.location.pathname)
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled()
    })
    expect(replaceStateSpy).not.toHaveBeenCalled()

    replaceStateSpy.mockRestore()
    sessionStorage.removeItem('ao_session_expired')
    sessionStorage.removeItem('ao_return_to')
  })

  it('handles unmount during bootstrap without calling setState', async () => {
    let resolveRefresh!: () => void
    mockRefresh.mockReturnValue(
      new Promise<void>((r) => {
        resolveRefresh = r
      })
    )

    const { unmount } = renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    unmount()

    await act(async () => {
      resolveRefresh()
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('does not restore location when returnTo is missing', async () => {
    mockRefresh.mockResolvedValue(undefined)
    sessionStorage.setItem('ao_session_expired', 'true')
    // No ao_return_to set
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

    renderWithAlerts(
      <AppLogin>
        <div>Content</div>
      </AppLogin>
    )

    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled()
    })
    expect(replaceStateSpy).not.toHaveBeenCalled()

    replaceStateSpy.mockRestore()
    sessionStorage.removeItem('ao_session_expired')
  })

  describe('auth_error URL parameter sanitization', () => {
    function setAuthErrorParam(value: string) {
      window.history.pushState({}, '', `/?auth_error=${encodeURIComponent(value)}`)
    }

    afterEach(() => {
      // Restore clean URL
      window.history.pushState({}, '', '/')
    })

    it('displays known error code as its mapped message', async () => {
      setAuthErrorParam('state_expired')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(screen.getByText('Login session expired. Please try again.')).toBeInTheDocument()
      })
    })

    it('displays generic fallback for unknown error codes', async () => {
      setAuthErrorParam('some_unknown_value')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(screen.getByText('Authentication failed. Please try again.')).toBeInTheDocument()
      })
      expect(screen.queryByText('some_unknown_value')).not.toBeInTheDocument()
    })

    it('displays generic fallback for attacker-crafted strings', async () => {
      setAuthErrorParam('<script>alert(1)</script>')

      renderWithAlerts(
        <AppLogin>
          <div>Content</div>
        </AppLogin>
      )

      await waitFor(() => {
        expect(screen.getByText('Authentication failed. Please try again.')).toBeInTheDocument()
      })
      expect(screen.queryByText('<script>alert(1)</script>')).not.toBeInTheDocument()
    })

    describe('with identity providers', () => {
      beforeEach(() => {
        mockProviders = [{ id: 'okta-1', name: 'Okta', provider_type: 'oidc' }]
      })

      it('shows logout failure Alert title for idp_logout_failed code', async () => {
        setAuthErrorParam('idp_logout_failed')

        renderWithAlerts(
          <AppLogin>
            <div>Content</div>
          </AppLogin>
        )

        await waitFor(() => {
          expect(screen.getByText('Identity provider sign-out failed')).toBeInTheDocument()
        })
        expect(
          screen.getByText('Logged out successfully, but could not log out of the identity provider.')
        ).toBeInTheDocument()
      })

      it('shows Authentication failed Alert title for non-logout error codes', async () => {
        setAuthErrorParam('auth_failed')

        renderWithAlerts(
          <AppLogin>
            <div>Content</div>
          </AppLogin>
        )

        await waitFor(() => {
          expect(screen.getByText('Authentication failed')).toBeInTheDocument()
        })
      })
    })
  })
})
