import { Flex, FlexItem, Stack, StackItem, Tab, TabContent, Tabs } from '@patternfly/react-core'
import { useId, useState } from 'react'
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
  const panelId = useId()
  const tabBarAction = useNodeFormTabBar()

  return (
    <Stack hasGutter style={{ height: '100%', minHeight: 0, flex: 1 }}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Tabs activeKey={activeTabKey} onSelect={(_event, key) => setActiveTabKey(Number(key))}>
              <Tab eventKey={0} title="Parameters" tabContentId={`${panelId}-parameters`} />
              {!hideSettingsTab && settingsContent !== undefined && (
                <Tab eventKey={1} title="Settings" tabContentId={`${panelId}-settings`} />
              )}
            </Tabs>
          </FlexItem>
          {tabBarAction && <FlexItem>{tabBarAction}</FlexItem>}
        </Flex>
      </StackItem>
      <SynPageBody>
        <Stack hasGutter>
          <StackItem>
            <TabContent id={`${panelId}-parameters`} aria-label="Parameters" hidden={activeTabKey !== 0}>
              {activeTabKey === 0 ? parametersContent : []}
            </TabContent>
            {!hideSettingsTab && settingsContent !== undefined && (
              <TabContent id={`${panelId}-settings`} aria-label="Settings" hidden={activeTabKey !== 1}>
                {activeTabKey === 1 ? settingsContent : []}
              </TabContent>
            )}
          </StackItem>
        </Stack>
      </SynPageBody>
    </Stack>
  )
}
