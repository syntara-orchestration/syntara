import { Flex, FlexItem, Stack, StackItem, Tab, Tabs } from '@patternfly/react-core'
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
  const tabBarAction = useNodeFormTabBar()
  const tabsId = useId()
  const parametersTabId = `${tabsId}-parameters-tab`
  const parametersPanelId = `${tabsId}-parameters-panel`
  const settingsTabId = `${tabsId}-settings-tab`
  const settingsPanelId = `${tabsId}-settings-panel`

  return (
    <Stack hasGutter style={{ height: '100%', minHeight: 0, flex: 1 }}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Tabs activeKey={activeTabKey} onSelect={(_event, key) => setActiveTabKey(Number(key))}>
              <Tab
                id={parametersTabId}
                tabContentId={parametersPanelId}
                eventKey={0}
                title="Parameters"
                aria-controls={parametersPanelId}
              />
              {!hideSettingsTab && settingsContent !== undefined && (
                <Tab
                  id={settingsTabId}
                  tabContentId={settingsPanelId}
                  eventKey={1}
                  title="Settings"
                  aria-controls={settingsPanelId}
                />
              )}
            </Tabs>
          </FlexItem>
          {tabBarAction && <FlexItem>{tabBarAction}</FlexItem>}
        </Flex>
      </StackItem>
      <SynPageBody>
        <div
          id={parametersPanelId}
          role="tabpanel"
          aria-labelledby={`pf-tab-0-${parametersTabId}`}
          hidden={activeTabKey !== 0}
        >
          {activeTabKey === 0 && (
            <Stack hasGutter>
              <StackItem>{parametersContent}</StackItem>
            </Stack>
          )}
        </div>
        {!hideSettingsTab && settingsContent !== undefined && (
          <div
            id={settingsPanelId}
            role="tabpanel"
            aria-labelledby={`pf-tab-1-${settingsTabId}`}
            hidden={activeTabKey !== 1}
          >
            {activeTabKey === 1 && (
              <Stack hasGutter>
                <StackItem>{settingsContent}</StackItem>
              </Stack>
            )}
          </div>
        )}
      </SynPageBody>
    </Stack>
  )
}
