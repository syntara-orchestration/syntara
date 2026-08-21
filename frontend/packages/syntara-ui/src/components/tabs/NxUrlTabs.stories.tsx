import { Content, Tab } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { createTestRouter } from '../../test/createTestRouter'
import { SynPanel } from '../layout/SynPanel'

import { NxUrlTabs } from './NxUrlTabs'

// Tab content follows the real-world pattern: each Tab panel owns its inner padding.
function TabPane({ label }: { label: string }) {
  return (
    <div style={{ padding: 'var(--pf-t--global--spacer--lg)' }}>
      <Content component="p">{label} tab content.</Content>
    </div>
  )
}

// Standard three tabs used across all stories.
// Multi-word labels ("Activity log", "Access roles") demonstrate the sentence-case rule.
function StandardTabs({ basePath, defaultTab }: { basePath: string; defaultTab?: string }) {
  return (
    <NxUrlTabs basePath={basePath} defaultTab={defaultTab ?? 'details'} aria-label="Resource tabs">
      <Tab eventKey="details" title="Details">
        <TabPane label="Details" />
      </Tab>
      <Tab eventKey="activity-log" title="Activity log">
        <TabPane label="Activity log" />
      </Tab>
      <Tab eventKey="access-roles" title="Access roles">
        <TabPane label="Access roles" />
      </Tab>
    </NxUrlTabs>
  )
}

const DefaultStoryRouter = createTestRouter('/resource/details')
function DefaultStory() {
  return (
    <DefaultStoryRouter>
      <SynPanel>
        <StandardTabs basePath="/resource" />
      </SynPanel>
    </DefaultStoryRouter>
  )
}

const SecondTabActiveRouter = createTestRouter('/resource/activity-log')
function SecondTabActiveStory() {
  return (
    <SecondTabActiveRouter>
      <SynPanel>
        <StandardTabs basePath="/resource" />
      </SynPanel>
    </SecondTabActiveRouter>
  )
}

const DefaultTabFallbackRouter = createTestRouter('/resource')
function DefaultTabFallbackStory() {
  // URL has no tab segment — `defaultTab` takes over without any redirect.
  return (
    <DefaultTabFallbackRouter>
      <SynPanel>
        <StandardTabs basePath="/resource" defaultTab="activity-log" />
      </SynPanel>
    </DefaultTabFallbackRouter>
  )
}

const ValidTabsRouter = createTestRouter('/resource/details')
function ValidTabsStory() {
  return (
    <ValidTabsRouter>
      <SynPanel>
        <NxUrlTabs
          basePath="/resource"
          defaultTab="details"
          validTabs={['details', 'activity-log', 'access-roles']}
          aria-label="Resource tabs"
        >
          <Tab eventKey="details" title="Details">
            <TabPane label="Details" />
          </Tab>
          <Tab eventKey="activity-log" title="Activity log">
            <TabPane label="Activity log" />
          </Tab>
          <Tab eventKey="access-roles" title="Access roles">
            <TabPane label="Access roles" />
          </Tab>
        </NxUrlTabs>
      </SynPanel>
    </ValidTabsRouter>
  )
}

const TabNavigationRouter = createTestRouter('/resource/details')
function TabNavigationStory() {
  return (
    <TabNavigationRouter>
      <SynPanel>
        <StandardTabs basePath="/resource" />
      </SynPanel>
    </TabNavigationRouter>
  )
}

const meta: Meta<typeof NxUrlTabs> = {
  component: NxUrlTabs,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'URL-driven tabs built on PatternFly `Tabs`. The active tab is derived from the URL path segment that immediately follows `basePath` — clicking a tab navigates via `setLocation` instead of updating local state.\n\n' +
          '**`basePath`** — the route prefix (e.g. `/settings`). The first path segment after it becomes the active tab key.\n\n' +
          '**`defaultTab`** — the tab shown when the URL has no segment after `basePath` (defaults to `"details"`).\n\n' +
          '**`validTabs`** — optional allowlist for pages whose tabs are loaded dynamically (e.g. from an API). If the URL names a tab not in this list, the component redirects (replace) to `defaultTab` — or the first valid tab if `defaultTab` is also absent from the list.\n\n' +
          'All other props are forwarded to PatternFly `Tabs`.\n\n' +
          '---\n\n' +
          '**UX guidelines (from the AO design system):**\n\n' +
          '- Tabs must live inside `SynPanel` (the `CompassPanel` equivalent), not outside it.\n' +
          '- Tab labels must use **sentence case** (e.g. "Activity log", not "Activity Log").\n' +
          '- Labels should be clear, professional, and action-oriented.\n' +
          '- Avoid colloquial language, slang, or informal phrasing in labels.\n' +
          '- Avoid punctuation in tab labels (no question marks or exclamation points).',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** First tab active — the URL segment matches the first tab key. `NxUrlTabs` lives inside `SynPanel`. */
export const Default: Story = {
  render: () => <DefaultStory />,
  parameters: {
    docs: {
      description: {
        story:
          'Basic three-tab configuration inside `SynPanel`. The initial URL points at `details`, so that tab is active. Multi-word labels ("Activity log", "Access roles") demonstrate the sentence-case convention.',
      },
    },
  },
}

/**
 * The URL points at the second tab (`/resource/activity-log`).
 * Shows that active-tab state is read from the URL on every render — not stored locally.
 */
export const NonDefaultTabActive: Story = {
  name: 'Non-default tab active',
  render: () => <SecondTabActiveStory />,
  parameters: {
    docs: {
      description: {
        story:
          'URL is `/resource/activity-log`, so the "Activity log" tab is active. The component does not manage its own active-tab state — the URL is the single source of truth.',
      },
    },
  },
}

/**
 * The URL has no tab segment (`/resource`). `defaultTab="activity-log"` kicks in and
 * the "Activity log" tab renders as active without any redirect.
 */
export const DefaultTabFallback: Story = {
  name: 'Default tab fallback',
  render: () => <DefaultTabFallbackStory />,
  parameters: {
    docs: {
      description: {
        story:
          'URL is `/resource` with no tab segment. `defaultTab="activity-log"` determines which tab is active. Use this prop to control which tab opens on a bare base-path visit.',
      },
    },
  },
}

/**
 * `validTabs` guards against stale or dynamically removed tabs.
 * When the current URL names a tab outside this list, `NxUrlTabs` replaces the history
 * entry with `defaultTab` (or the first entry in `validTabs`).
 */
export const WithValidTabs: Story = {
  name: 'Valid tabs guard',
  render: () => <ValidTabsStory />,
  parameters: {
    docs: {
      description: {
        story:
          'Use `validTabs` when the tab list is populated from an API and may change. If the URL contains a tab key that is absent from `validTabs`, the component silently redirects to `defaultTab`. Here the URL is already valid, so no redirect occurs.',
      },
    },
  },
}

/** Clicking a tab updates the active selection via URL navigation. */
export const TabNavigation: Story = {
  name: 'Tab navigation',
  render: () => <TabNavigationStory />,
  parameters: {
    docs: {
      description: {
        story:
          'Demonstrates that clicking a tab calls `setLocation` to update the URL, which drives the `activeKey` on the next render. Click any tab to see the selection update.',
      },
    },
  },
}
