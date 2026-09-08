import { Button, Content, StackItem } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'

import { SynErrorState } from '../states/SynErrorState'

import { SynPage, SynPageBody } from './SynPage'
import { SynPageHeader } from './SynPageHeader'
import { SynPanel } from './SynPanel'
import { SynPanelContentStack } from './SynPanelContentStack'
import { SynPanelStack, SynPanelStackItem } from './SynPanelStack'

const meta: Meta<typeof SynPage> = {
  component: SynPage,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          '`SynPage` + `SynPageHeader` + `SynPageBody` form the standard page layout skeleton.\n\n' +
          '`SynPageBody` is the main content area below the header. ' +
          'Pass `isCentered` to center content on both axes — use this for loading spinners and empty states.',
      },
    },
  },
  decorators: [
    (Story) => (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '400px',
          border: '1px dashed var(--pf-t--global--border--color--default)',
        }}
      >
        <Story />
      </div>
    ),
  ],
}
export default meta

type Story = StoryObj<typeof meta>

export const FullListPageLayout: Story = {
  name: 'Full list page layout',
  parameters: {
    docs: {
      description: {
        story:
          'Standard list page layout: fixed filter bar row above a filled table area, with horizontal inset padding.',
      },
    },
  },
  render: () => (
    <SynPage>
      <SynPageHeader title="Workflows" toolbar={<Button variant="primary">Create workflow</Button>} />
      <SynPageBody>
        <SynPanel isFullHeight>
          <SynPanelContentStack variant="inset">
            <StackItem>
              <Content component="p">Filter bar</Content>
            </StackItem>
            <StackItem isFilled>
              <Content component="p">Table content area</Content>
            </StackItem>
          </SynPanelContentStack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  ),
}

export const FullDetailPageLayout: Story = {
  name: 'Full detail page layout (breadcrumbs)',
  parameters: {
    docs: {
      description: {
        story: 'Detail page with breadcrumb navigation. Use when the user drills into a specific resource from a list.',
      },
    },
  },
  render: () => (
    <SynPage>
      <SynPageHeader
        title="my-workflow"
        breadcrumbs={[{ label: 'Workflows', href: '/workflows' }, { label: 'my-workflow' }]}
      />
      <SynPageBody>
        <SynPanel isFullHeight>
          <SynPanelContentStack>
            <StackItem>
              <Content component="p">Tab bar</Content>
            </StackItem>
            <StackItem isFilled>
              <Content component="p">Tab content area</Content>
            </StackItem>
          </SynPanelContentStack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  ),
}

export const FullFormPageLayout: Story = {
  name: 'Full form page layout (breadcrumbs + toolbar)',
  parameters: {
    docs: {
      description: {
        story: 'Create/edit form page with breadcrumb trail and Save/Cancel toolbar.',
      },
    },
  },
  render: () => (
    <SynPage>
      <SynPageHeader
        title="Create user"
        breadcrumbs={[
          { label: 'Access management', href: '/access-management' },
          { label: 'Users', href: '/access-management/users' },
          { label: 'Create user' },
        ]}
        toolbar={
          <>
            <Button variant="secondary">Cancel</Button>
            <Button variant="primary">Save</Button>
          </>
        }
      />
      <SynPageBody>
        <SynPanel>
          <Content component="p">Form fields</Content>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  ),
}

export const ErrorPageLayout: Story = {
  name: 'Error state in panel',
  parameters: {
    docs: {
      description: {
        story:
          'Error states live inside `SynPanel` within the page body — the same panel that normally holds table or form content.',
      },
    },
  },
  render: () => (
    <SynPage>
      <SynPageHeader title="Workflows" toolbar={<Button variant="primary">Create workflow</Button>} />
      <SynPageBody isCentered>
        <SynPanel isFullHeight>
          <SynErrorState message={{ detail: 'Connection timed out.', retryable: true }} onRetry={fn()} />
        </SynPanel>
      </SynPageBody>
    </SynPage>
  ),
}

export const StackedPanelsLayout: Story = {
  name: 'Stacked panels (canvas + details)',
  parameters: {
    docs: {
      description: {
        story:
          'Two sibling `SynPanel`s in `SynPanelStack`. Do not wrap them in `overflow: hidden` — that clips panel box-shadow.',
      },
    },
  },
  render: () => (
    <SynPage>
      <SynPageHeader title="Workflow run" />
      <SynPageBody>
        <SynPanelStack>
          <SynPanelStackItem isFilled>
            <SynPanel isFullHeight>
              <Content component="p">Canvas</Content>
            </SynPanel>
          </SynPanelStackItem>
          <SynPanelStackItem style={{ height: '120px' }}>
            <SynPanel isFullHeight>
              <Content component="p">Current run details</Content>
            </SynPanel>
          </SynPanelStackItem>
        </SynPanelStack>
      </SynPageBody>
    </SynPage>
  ),
}
