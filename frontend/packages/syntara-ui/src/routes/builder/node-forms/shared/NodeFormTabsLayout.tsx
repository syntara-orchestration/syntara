import { Flex, FlexItem, Stack, StackItem, Tab, Tabs } from '@patternfly/react-core'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { SynPageBody } from '../../../../components/layout/SynPage'

import { useNodeFormTabBar } from './useNodeFormTabBar'

type NodeFormTabsLayoutProps = {
  parametersContent: ReactNode
  settingsContent?: ReactNode
  /** When true, the Settings tab is not rendered. Use for node types with no configurable settings (e.g. condition, switch). */
  hideSettingsTab?: boolean
}

export function NodeFormTabsLayout({ parametersContent, settingsContent, hideSettingsTab }: NodeFormTabsLayoutProps) {
  const [activeTabKey, setActiveTabKey] = useState<number>(0)
  const tabBarAction = useNodeFormTabBar()

  return (
    <Stack hasGutter style={{ height: '100%', minHeight: 0, flex: 1 }}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Tabs activeKey={activeTabKey} onSelect={(_event, key) => setActiveTabKey(Number(key))}>
              <Tab eventKey={0} title="Parameters" />
              {!hideSettingsTab && settingsContent !== undefined && <Tab eventKey={1} title="Settings" />}
            </Tabs>
          </FlexItem>
          {tabBarAction && <FlexItem>{tabBarAction}</FlexItem>}
        </Flex>
      </StackItem>
      <SynPageBody>
        <Stack hasGutter>
          <StackItem>{activeTabKey === 0 ? parametersContent : (settingsContent ?? null)}</StackItem>
        </Stack>
      </SynPageBody>
    </Stack>
  )
}
