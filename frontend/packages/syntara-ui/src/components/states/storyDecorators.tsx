import type { Decorator } from '@storybook/react-vite'

import { SynPage, SynPageBody } from '../layout/SynPage'
import { SynPageHeader } from '../layout/SynPageHeader'
import { SynPanel } from '../layout/SynPanel'

export const pageDecorator: Decorator = (Story) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      height: '400px',
      border: '1px dashed var(--pf-t--global--border--color--default)',
    }}
  >
    <SynPage>
      <SynPageHeader title="Workflows" />
      <SynPageBody isCentered>
        <SynPanel isFullHeight>
          <Story />
        </SynPanel>
      </SynPageBody>
    </SynPage>
  </div>
)
