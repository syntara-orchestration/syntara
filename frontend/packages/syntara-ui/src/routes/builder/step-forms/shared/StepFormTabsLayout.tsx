import { Flex, FlexItem, Stack, StackItem, Tab, Tabs } from '@patternfly/react-core'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { SynPageBody } from '../../../../components/layout/SynPage'

import { useStepFormTabBar } from './useStepFormTabBar'

type StepFormTabKey = 'parameters' | 'execution' | 'settings'

type StepFormTabsLayoutProps = Readonly<{
  parametersContent: ReactNode
  /** When provided, inserts an Execution tab between Parameters and Settings. */
  executionContent?: ReactNode
  settingsContent?: ReactNode
  /** When true, the Settings tab is not rendered. Use for step types with no configurable settings (e.g. condition, switch). */
  hideSettingsTab?: boolean
}>

function tabContent(
  activeTabKey: StepFormTabKey,
  parametersContent: ReactNode,
  executionContent: ReactNode | undefined,
  settingsContent: ReactNode | undefined
): ReactNode {
  if (activeTabKey === 'execution') {
    return executionContent ?? null
  }
  if (activeTabKey === 'settings') {
    return settingsContent ?? null
  }
  return parametersContent
}

export function StepFormTabsLayout({
  parametersContent,
  executionContent,
  settingsContent,
  hideSettingsTab,
}: StepFormTabsLayoutProps) {
  const [activeTabKey, setActiveTabKey] = useState<StepFormTabKey>('parameters')
  const tabBarAction = useStepFormTabBar()
  const showExecutionTab = executionContent !== undefined
  const showSettingsTab = !hideSettingsTab && settingsContent !== undefined

  return (
    <Stack hasGutter style={{ height: '100%', minHeight: 0, flex: 1 }}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Tabs activeKey={activeTabKey} onSelect={(_event, key) => setActiveTabKey(key as StepFormTabKey)}>
              <Tab eventKey="parameters" title="Parameters" />
              {showExecutionTab && <Tab eventKey="execution" title="Execution" />}
              {showSettingsTab && <Tab eventKey="settings" title="Settings" />}
            </Tabs>
          </FlexItem>
          {tabBarAction && <FlexItem>{tabBarAction}</FlexItem>}
        </Flex>
      </StackItem>
      <SynPageBody>
        <Stack hasGutter>
          <StackItem>{tabContent(activeTabKey, parametersContent, executionContent, settingsContent)}</StackItem>
        </Stack>
      </SynPageBody>
    </Stack>
  )
}
