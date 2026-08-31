import { Content } from '@patternfly/react-core'
import type { Decorator, Meta, StoryObj } from '@storybook/react-vite'

import { SynPanel } from './SynPanel'

const PANEL_CONTENT = (
  <Content component="p">
    Panel content area. This panel wraps PatternFly&apos;s <code>Panel → PanelMain → PanelMainBody</code> composition.
  </Content>
)

const heightConstraintDecorator: Decorator = (Story) => (
  <div style={{ height: '200px', display: 'flex', flexDirection: 'column' }}>
    <Story />
  </div>
)

const meta: Meta<typeof SynPanel> = {
  component: SynPanel,
  tags: ['autodocs'],
  args: {
    children: PANEL_CONTENT,
  },
  parameters: {
    docs: {
      description: {
        component:
          'Content panel used on every page to frame the main content area.\n\n' +
          '**Variants:** use `variant="raised"` for floating controls that need elevation (canvas overlays, step nodes); ' +
          '`opaqueFloatingFill` for a solid background without the raised chrome.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Default glass panel. `isGlass` defaults on unless `isPill` or `variant="raised"` is set. */
export const Default: Story = {}

/** Full raised look — shadow and smaller corner radius. `isGlass` is disabled automatically. */
export const Raised: Story = {
  args: { variant: 'raised' },
}

/**
 * Opaque floating-token fill without the `variant="raised"` chrome (no shadow / smaller radius).
 * Use when you want a solid background under the glass theme without extra elevation styling.
 */
export const OpaqueFloatingFill: Story = {
  args: { opaqueFloatingFill: true },
}

/** Pill-shaped panel. `isGlass` is disabled automatically when `isPill` is set. */
export const Pill: Story = {
  args: { isPill: true },
}

/** `hasNoPadding` removes inner body padding — useful when a child element owns its own spacing. */
export const NoPadding: Story = {
  args: {
    hasNoPadding: true,
    children: (
      <div
        style={{
          padding: 'var(--pf-t--global--spacer--md)',
          background: 'var(--pf-t--global--background--color--secondary--default)',
        }}
      >
        <Content component="p">Custom padded region inside a no-padding panel.</Content>
      </div>
    ),
  },
}

/**
 * `isScrollable + isFullHeight` — inner body grows to fill available space and scrolls.
 * `isAutoHeight` is set automatically when both flags are true (pass `isAutoHeight={false}` to opt out).
 */
export const Scrollable: Story = {
  decorators: [heightConstraintDecorator],
  args: {
    isScrollable: true,
    isFullHeight: true,
    children: (
      <>
        {Array.from({ length: 12 }, (_, i) => (
          <Content key={i} component="p">
            Row {i + 1} — overflow content to demonstrate scrollable panel behaviour.
          </Content>
        ))}
      </>
    ),
  },
}
