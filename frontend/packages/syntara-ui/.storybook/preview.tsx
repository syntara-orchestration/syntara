import type { Preview } from '@storybook/tanstack-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useMemo, type ReactNode } from 'react'

// Storybook renders stories in an iframe, outside the routes that normally load React Flow's required canvas styles.
import '@xyflow/react/dist/style.css'
import '../src/index.css'
import type { ColorSchemePreference } from '../src/providers/theme/colorScheme'
import { ColorSchemeProvider } from '../src/providers/theme/ColorSchemeProvider'
import { ensureDocumentTheme } from '../src/providers/theme/documentTheme'
import { useColorScheme } from '../src/providers/theme/useColorScheme'

// Prevent FOUC: apply theme classes before React mounts (mirrors the inline script in index.html).
// index.html sets these on the real app's <html>; Storybook's iframe has no equivalent bootstrap.
ensureDocumentTheme()

function isColorSchemePreference(value: string): value is ColorSchemePreference {
  return value === 'system' || value === 'light' || value === 'dark'
}

// Bridges the toolbar global to ColorSchemeProvider. Must remain a child of ColorSchemeProvider
// so it can call useColorScheme(); moving it outside will throw at runtime.
function ThemeSync({ toolbarValue, children }: { toolbarValue: string; children: ReactNode }) {
  const { setColorScheme } = useColorScheme()

  useEffect(() => {
    if (isColorSchemePreference(toolbarValue)) {
      setColorScheme(toolbarValue)
    }
  }, [toolbarValue, setColorScheme])

  return <>{children}</>
}

const preview: Preview = {
  globalTypes: {
    colorScheme: {
      name: 'Color Scheme',
      description: 'Toggle light/dark mode',
      toolbar: {
        icon: 'mirror',
        title: 'Color Scheme',
        items: [
          { value: 'system', title: 'System', icon: 'browser' },
          { value: 'light', title: 'Light', icon: 'sun' },
          { value: 'dark', title: 'Dark', icon: 'moon' },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    colorScheme: 'system',
  },
  decorators: [
    (Story, context: { globals: Record<string, string> }) => {
      const client = useMemo(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }), [])
      const colorScheme = context.globals['colorScheme'] ?? 'system'
      return (
        <ColorSchemeProvider>
          <ThemeSync toolbarValue={colorScheme}>
            <QueryClientProvider client={client}>
              <Story />
            </QueryClientProvider>
          </ThemeSync>
        </ColorSchemeProvider>
      )
    },
  ],
  parameters: {
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
    options: {
      storySort: { method: 'alphabetical' },
    },
  },
}

export default preview
