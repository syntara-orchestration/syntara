import { Content } from '@patternfly/react-core'
import type { Decorator, Meta, StoryObj } from '@storybook/react-vite'

import { SynPanel } from './SynPanel'
import { SynPanelStack, SynPanelStackItem } from './SynPanelStack'

const heightDecorator: Decorator = (Story) => (
  <div
    style={{
      height: '360px',
      display: 'flex',
      flexDirection: 'column',
      padding: 'var(--pf-t--global--spacer--md)',
      background: 'var(--pf-t--global--background--color--secondary--default)',
    }}
  >
    <Story />
  </div>
)

const meta: Meta<typeof SynPanelStack> = {
  component: SynPanelStack,
  tags: ['autodocs'],
  decorators: [heightDecorator],
  parameters: {
    docs: {
      description: {
        component:
          'Full-height column for stacking sibling `SynPanel`s (canvas + details, editor + run panel).\n\n' +
          'Keeps `overflow: visible` and `min-height: 0` so PatternFly panel `box-shadow` is not clipped. ' +
          'Put overflow clipping inside each panel, not on this stack.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/**
 * Two full-height panels stacked in one page body. Shadows should render fully against
 * the page background — this is the execution-detail / builder live-run split.
 */
export const StackedPanels: Story = {
  render: () => (
    <SynPanelStack>
      <SynPanelStackItem isFilled>
        <SynPanel isFullHeight>
          <Content component="p">Canvas / primary pane</Content>
        </SynPanel>
      </SynPanelStackItem>
      <SynPanelStackItem style={{ height: '120px' }}>
        <SynPanel isFullHeight>
          <Content component="p">Details / secondary pane</Content>
        </SynPanel>
      </SynPanelStackItem>
    </SynPanelStack>
  ),
}
