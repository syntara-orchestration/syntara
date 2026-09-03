// Leave VITE_EXTENDED unset so unit tests stay on the community default title (Syntara).

import '@testing-library/jest-dom/vitest'
import 'vitest-axe/extend-expect'
import { cleanup } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeAll, beforeEach, afterAll, expect, vi } from 'vitest'

const listeners = new Set<() => void>()
function notifyListeners() {
  listeners.forEach((l) => l())
}

function applyUrlUpdate(url: string) {
  const qIndex = url.indexOf('?')
  const newPathname = qIndex >= 0 ? url.slice(0, qIndex) : url
  const newSearchStr = qIndex >= 0 ? url.slice(qIndex) : ''
  if (newPathname === routerTestState.pathname && newSearchStr === routerTestState.searchStr) return
  routerTestState.pathname = newPathname
  routerTestState.searchStr = newSearchStr
  notifyListeners()
}

export const mockUseSearch = vi.fn(() => ({}))

export function MockLink({
  to,
  children,
  className,
  style,
  ...rest
}: {
  to: string
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return React.createElement('a', { href: String(to), className, style, ...rest }, children)
}

export const routerTestState = {
  pathname: '/',
  searchStr: '',
  navigate: vi.fn((...args: unknown[]) => {
    const arg = args[0]
    if (arg && typeof arg === 'object' && 'to' in arg) {
      applyUrlUpdate(String((arg as { to: string }).to))
    }
    return Promise.resolve()
  }),
  historyPush: vi.fn((url: string) => {
    applyUrlUpdate(url)
  }),
}

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-router')>('@tanstack/react-router')
  return {
    ...actual,
    Link: MockLink,
    useSearch: mockUseSearch,
    useNavigate: () => routerTestState.navigate,
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const subscribe = React.useCallback((cb: () => void) => {
        listeners.add(cb)
        return () => {
          listeners.delete(cb)
        }
      }, [])
      React.useSyncExternalStore(subscribe, () => routerTestState.pathname + '\0' + routerTestState.searchStr)
      const state = { location: { pathname: routerTestState.pathname, searchStr: routerTestState.searchStr } }
      return opts?.select ? opts.select(state) : state
    },
    useRouter: () => ({
      history: { push: routerTestState.historyPush },
      state: { location: { pathname: routerTestState.pathname, searchStr: routerTestState.searchStr } },
    }),
    useBlocker: () => ({ status: 'idle' }),
    useParams: vi.fn(() => ({})),
    useMatch: vi.fn(() => ({ params: {} })),
  }
})

// Stub the Monaco-backed CodeEditor: @monaco-editor/loader defaults to injecting a
// <script src="https://cdn..."> tag to fetch Monaco from a CDN. happy-dom throws a
// DOMException for the blocked load, which surfaces as an unhandled rejection and fails the
// vitest process (non-zero exit) even though every assertion still passes. Test files that need
// finer control over the editor (drag/drop, expand button, etc.) already declare their own
// vi.mock('@patternfly/react-code-editor', ...), which takes precedence over this one.
vi.mock('@patternfly/react-code-editor', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@patternfly/react-code-editor')>()
  return {
    ...actual,
    CodeEditor: ({
      code,
      onCodeChange,
      customControls,
      'aria-label': ariaLabel,
    }: {
      code?: string
      onCodeChange?: (code: string) => void
      customControls?: React.ReactNode
      'aria-label'?: string
    }) =>
      React.createElement(
        'div',
        { 'data-testid': 'code-editor', 'aria-label': ariaLabel },
        React.createElement('textarea', {
          'data-testid': 'code-textarea',
          value: code,
          onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => onCodeChange?.(e.target.value),
          'aria-label': ariaLabel,
        }),
        customControls
      ),
  }
})

import { resetPollingConnectionCounter } from '../routes/builder/utils/edgeConnectionHelpers'

// Collect React act() warnings during each test, then fail in afterEach.
// Throwing directly from console.error creates unhandled rejections when
// async third-party code (e.g. PatternFly Popper) triggers the warning.
let actWarnings: string[] = []

/* eslint-disable no-console */
const originalConsoleError = console.error
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    const message = args[0]
    if (typeof message === 'string') {
      if (message.includes('is unrecognized in this browser')) {
        return
      }
      const isActWarning = [
        'was not wrapped in act',
        'overlapping act() calls',
        'act(async () => ...) without await',
        'Do not await the result of calling act',
      ].some((pattern) => message.includes(pattern))

      if (isActWarning) {
        const renderedArgs = args.map((arg) => String(arg))
        const warningHeader = renderedArgs.slice(0, 2).join(' ')
        const isPF6InternalWarning =
          message.includes('was not wrapped in act') && /\b(Popper|Tabs)\b/.test(warningHeader)
        if (!isPF6InternalWarning) {
          actWarnings.push(renderedArgs.join(' '))
        }
        return
      }
    }
    originalConsoleError.apply(console, args)
  }
})
afterAll(() => {
  console.error = originalConsoleError
})
/* eslint-enable no-console */

// Polyfill for Web Animations API getAnimations method (not supported in happy-dom)
if (typeof Element !== 'undefined' && !Element.prototype.getAnimations) {
  Element.prototype.getAnimations = function () {
    return []
  }
}

// Polyfill for ResizeObserver (not supported in happy-dom)
if (typeof globalThis !== 'undefined' && !globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {
      // No-op in test environment
    }
    unobserve() {
      // No-op in test environment
    }
    disconnect() {
      // No-op in test environment
    }
  } as typeof ResizeObserver
}

// Polyfill the `[hidden] { display: none }` UA-stylesheet rule (missing in happy-dom,
// which only maps default display per tag name, not by attribute — this makes
// getComputedStyle().display agree with the `hidden` attribute so axe-core's
// visibility check doesn't flag legitimately hidden elements as unlabeled).
if (typeof document !== 'undefined') {
  const hiddenAttributeStyle = document.createElement('style')
  hiddenAttributeStyle.textContent = '[hidden] { display: none !important; }'
  document.head.appendChild(hiddenAttributeStyle)
}

beforeEach(() => {
  actWarnings = []
  routerTestState.pathname = '/'
  routerTestState.searchStr = ''
  routerTestState.navigate.mockClear()
  routerTestState.historyPush.mockClear()
  mockUseSearch.mockReset().mockReturnValue({})
  listeners.clear()
  // SECURITY: Reset edge connection counter to prevent test failures from concurrency limit
  resetPollingConnectionCounter()
})

afterEach(async () => {
  await Promise.resolve()
  cleanup()
  await Promise.resolve()
  const warnings = [...actWarnings]
  actWarnings = []
  expect(
    warnings,
    `React act() warnings in: ${warnings.join(', ')} — wrap state updates in waitFor or act`
  ).toHaveLength(0)
})
