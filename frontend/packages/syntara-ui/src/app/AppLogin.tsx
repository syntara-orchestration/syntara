import {
  ActionGroup,
  Alert,
  Brand,
  Bullseye,
  Button,
  Content,
  Divider,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Icon,
  Login,
  LoginHeader,
  LoginMainBody,
  LoginMainHeader,
  TextInput,
  ValidatedOptions,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

import { RETURN_TO_KEY, SESSION_EXPIRED_KEY } from '../components/session/sessionTimeoutConstants'
import { SynLoadingState } from '../components/states/SynLoadingState'
import { useBrand } from '../providers/brand'
import { useColorScheme } from '../providers/theme/useColorScheme'
import { AuthError, useAuthStore, selectIsAuthenticated, selectIsRefreshing } from '../stores/useAuthStore'

import styles from './AppLogin.module.css'
import { resolveAuthError } from './authErrorMessages'
import { IdentityProviderButtons } from './IdentityProviderButtons'
import { useAuthProviders } from './useAuthProviders'

const INCORRECT_CREDENTIALS_MESSAGE = 'Incorrect login credentials'

/**
 * After a session timeout, restore the user's previous location.
 *
 * Only restores when the `SESSION_EXPIRED_KEY` flag is present — this
 * ensures manual logout (which never sets the flag) does not accidentally
 * restore a stale location. Clears both keys after consuming them.
 */
function consumeSessionExpiredReturnUrl(): void {
  const wasTimeout = sessionStorage.getItem(SESSION_EXPIRED_KEY)
  sessionStorage.removeItem(SESSION_EXPIRED_KEY)
  const returnTo = sessionStorage.getItem(RETURN_TO_KEY)
  sessionStorage.removeItem(RETURN_TO_KEY)

  if (!wasTimeout || !returnTo) return

  if (
    returnTo.startsWith('/') &&
    !returnTo.includes('://') &&
    returnTo !== '/' &&
    returnTo !== window.location.pathname
  ) {
    window.history.replaceState({}, '', returnTo)
  }
}

function mapLoginError(err: unknown): string {
  if (err instanceof AuthError && err.code === 'AUTHENTICATION_REQUIRED') {
    return INCORRECT_CREDENTIALS_MESSAGE
  }
  if (err instanceof Error) return err.message || INCORRECT_CREDENTIALS_MESSAGE
  return INCORRECT_CREDENTIALS_MESSAGE
}

const LoginErrorField = {
  Username: 'username',
  Password: 'password',
  Credentials: 'credentials',
} as const

type LoginErrorField = (typeof LoginErrorField)[keyof typeof LoginErrorField]

type LocalLoginFormProps = {
  username: string
  password: string
  loginError: string | null
  loginErrorField: LoginErrorField | null
  isLoggingIn: boolean
  loginButtonLabel: string
  onChangeUsername: (value: string) => void
  onChangePassword: (value: string) => void
  onClearError: () => void
  onLogin: (e: React.MouseEvent<HTMLButtonElement>) => void
}

function LocalLoginForm({
  username,
  password,
  loginError,
  loginErrorField,
  isLoggingIn,
  loginButtonLabel,
  onChangeUsername,
  onChangePassword,
  onClearError,
  onLogin,
}: Readonly<LocalLoginFormProps>) {
  const isValidUsername =
    loginErrorField !== LoginErrorField.Username && loginErrorField !== LoginErrorField.Credentials
  const isValidPassword =
    loginErrorField !== LoginErrorField.Password && loginErrorField !== LoginErrorField.Credentials

  return (
    <Form onSubmit={(e) => e.preventDefault()}>
      {loginError !== null && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem
              variant={!isValidUsername || !isValidPassword ? 'error' : 'default'}
              icon={
                <Icon status="danger">
                  <RhUiErrorIcon />
                </Icon>
              }
            >
              {loginError}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
      <FormGroup label="Username" isRequired fieldId="pf-login-username-id">
        <TextInput
          id="pf-login-username-id"
          isRequired
          validated={isValidUsername ? ValidatedOptions.default : ValidatedOptions.error}
          type="text"
          name="pf-login-username-id"
          value={username}
          onChange={(_e, val) => {
            onChangeUsername(val)
            onClearError()
          }}
        />
      </FormGroup>
      <FormGroup label="Password" isRequired fieldId="pf-login-password-id">
        <TextInput
          isRequired
          type="password"
          autoComplete="current-password"
          id="pf-login-password-id"
          name="pf-login-password-id"
          validated={isValidPassword ? ValidatedOptions.default : ValidatedOptions.error}
          value={password}
          onChange={(_e, val) => {
            onChangePassword(val)
            onClearError()
          }}
        />
      </FormGroup>
      <ActionGroup>
        <Button variant="primary" type="submit" onClick={onLogin} isBlock isDisabled={isLoggingIn}>
          {loginButtonLabel}
        </Button>
      </ActionGroup>
    </Form>
  )
}

const toggleLinkStyle: React.CSSProperties = { textDecoration: 'underline', textDecorationStyle: 'dashed' }

export function AppLogin(props: { children?: ReactNode }) {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const logoutCount = useAuthStore((s) => s.logoutCount)

  if (isAuthenticated) {
    return props.children
  }

  return <AppLoginForm key={logoutCount} />
}

function AppLoginForm() {
  const brand = useBrand()
  const { colorScheme } = useColorScheme()
  const loginLogo = colorScheme === 'dark' ? brand.logoLoginDark : brand.logoLoginLight
  const isRefreshing = useAuthStore(selectIsRefreshing)
  const login = useAuthStore((s) => s.login)
  const refresh = useAuthStore((s) => s.refresh)
  const [bootstrapDone, setBootstrapDone] = useState(false)
  const [isLoggingIn, setIsLoggingIn] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [sessionExpiredMessage] = useState(() => {
    const expired = sessionStorage.getItem(SESSION_EXPIRED_KEY)
    if (expired) return 'Your session has expired due to inactivity. Please log in again.'
    return null
  })

  const [initialAuthError] = useState(() => {
    const raw = new URLSearchParams(globalThis.location.search).get('auth_error')
    if (raw) {
      // Clean up the URL so the error doesn't persist on refresh.
      // replaceState is a browser API (not React state), so calling it
      // in the initializer is safe and avoids an extra render cycle.
      globalThis.history.replaceState({}, '', globalThis.location.pathname)
      return resolveAuthError(raw)
    }
    return null
  })
  const [loginError, setLoginError] = useState<string | null>(initialAuthError?.message ?? null)
  const [loginErrorField, setLoginErrorField] = useState<LoginErrorField | null>(
    initialAuthError ? LoginErrorField.Credentials : null
  )
  const [isLogoutError, setIsLogoutError] = useState(initialAuthError?.isLogoutFailure ?? false)
  const [showLocalLogin, setShowLocalLogin] = useState(false)
  const bootstrapAttempted = useRef(false)

  const { providers, isLoading: providersLoading } = useAuthProviders()
  const hasProviders = providers.length > 0

  // On mount, try a silent refresh from the HttpOnly cookie
  useEffect(() => {
    if (useAuthStore.getState().isAuthenticated || bootstrapAttempted.current) return
    bootstrapAttempted.current = true

    let cancelled = false

    async function bootstrapAuthFromCookie(): Promise<void> {
      try {
        await refresh()
        consumeSessionExpiredReturnUrl()
      } catch {
        // No valid cookie — user needs to enter credentials
        useAuthStore.setState({ error: null })
      } finally {
        if (!cancelled) {
          setBootstrapDone(true)
        }
      }
    }

    // Completion and errors are handled inside bootstrapAuthFromCookie (not detached / not reportError-only).
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- intentional fire-and-forget from sync useEffect
    bootstrapAuthFromCookie()

    return () => {
      cancelled = true
      // Strict Mode remount (or `[refresh]` identity change) must be allowed to run bootstrap again;
      // otherwise `bootstrapDone` never flips and the login shell spins forever.
      bootstrapAttempted.current = false
    }
  }, [refresh])

  const handleLogin = useCallback(
    (e: React.MouseEvent<HTMLButtonElement>) => {
      e.preventDefault()
      if (!username) {
        setLoginError('Enter your username')
        setLoginErrorField(LoginErrorField.Username)
        return
      }
      if (!password) {
        setLoginError('Enter your password')
        setLoginErrorField(LoginErrorField.Password)
        return
      }
      setLoginError(null)
      setLoginErrorField(null)
      setIsLoggingIn(true)
      login({ username, password })
        .then(consumeSessionExpiredReturnUrl)
        .catch((err: unknown) => {
          setIsLoggingIn(false)
          setPassword('')
          setLoginError(mapLoginError(err))
          setLoginErrorField(LoginErrorField.Credentials)
          setIsLogoutError(false)
        })
    },
    [username, password, login]
  )

  const clearError = useCallback(() => {
    setLoginError(null)
    setLoginErrorField(null)
  }, [])

  const localFormProps: LocalLoginFormProps = {
    username,
    password,
    loginError,
    loginErrorField,
    isLoggingIn,
    loginButtonLabel: 'Log in',
    onChangeUsername: setUsername,
    onChangePassword: setPassword,
    onClearError: clearError,
    onLogin: handleLogin,
  }

  if (!bootstrapDone || isRefreshing || providersLoading) {
    return (
      <Bullseye style={{ height: '100vh' }}>
        <SynLoadingState />
      </Bullseye>
    )
  }

  const sessionExpiredAlert = sessionExpiredMessage ? (
    <Alert
      variant="info"
      title={sessionExpiredMessage}
      isInline
      style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}
    />
  ) : null

  const header = (
    <LoginHeader>
      <Brand src={loginLogo} alt={brand.appTitle} className={`${styles.loginLogo} vr-login-brand-logo`} />
    </LoginHeader>
  )

  // State A: No IDPs — show original login form
  if (!hasProviders) {
    return (
      <Login header={header}>
        <LoginMainHeader title={`Log in to ${brand.appTitle}`} subtitle="Enter your credentials to continue" />
        <LoginMainBody>
          {sessionExpiredAlert}
          <LocalLoginForm {...localFormProps} />
        </LoginMainBody>
      </Login>
    )
  }

  // State B/C: IDPs exist
  return (
    <Login header={header}>
      <LoginMainHeader
        title={`Log in to ${brand.appTitle}`}
        subtitle={`Select your identity provider to access ${brand.appTitle}. Contact your administrator if you need assistance.`}
      />
      <LoginMainBody>
        {sessionExpiredAlert}

        {loginError && loginErrorField === LoginErrorField.Credentials && (
          <Alert
            variant="danger"
            title={isLogoutError ? 'Identity provider sign-out failed' : 'Authentication failed'}
            isInline
            style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}
          >
            {loginError}
          </Alert>
        )}

        <IdentityProviderButtons providers={providers} />

        {showLocalLogin ? (
          <>
            <Divider
              style={{ marginTop: 'var(--pf-t--global--spacer--lg)', marginBottom: 'var(--pf-t--global--spacer--lg)' }}
            />
            <HelperText style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
              <HelperTextItem>
                For local account access only. Other users should sign in using the identity provider above.
              </HelperTextItem>
            </HelperText>
            <LocalLoginForm {...localFormProps} />
            <Content style={{ marginTop: 'var(--pf-t--global--spacer--md)', textAlign: 'center' }}>
              <Button variant="link" onClick={() => setShowLocalLogin(false)} style={toggleLinkStyle}>
                Hide local account login
              </Button>
            </Content>
          </>
        ) : (
          <Content style={{ marginTop: 'var(--pf-t--global--spacer--lg)', textAlign: 'center' }}>
            <Button variant="link" onClick={() => setShowLocalLogin(true)} style={toggleLinkStyle}>
              Sign in using local account
            </Button>
          </Content>
        )}
      </LoginMainBody>
    </Login>
  )
}
