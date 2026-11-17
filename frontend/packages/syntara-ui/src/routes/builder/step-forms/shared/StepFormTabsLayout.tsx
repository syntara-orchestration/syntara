import { Flex, FlexItem, Stack, StackItem, Tab, Tabs } from '@patternfly/react-core'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { SynPageBody } from '../../../../components/layout/SynPage'

import stepFormStyles from './stepFormStyles.module.css'
import { useStepFormTabBar } from './useStepFormTabBar'

type StepFormTabsLayoutProps = {
  parametersContent: ReactNode
  settingsContent?: ReactNode
  /** When true, the Settings tab is not rendered. Use for step types with no configurable settings (e.g. condition, switch). */
  hideSettingsTab?: boolean
}

export function StepFormTabsLayout({ parametersContent, settingsContent, hideSettingsTab }: StepFormTabsLayoutProps) {
  const [activeTabKey, setActiveTabKey] = useState<number>(0)
  const tabBarAction = useStepFormTabBar()

  return (
    <Stack hasGutter className={stepFormStyles.nodeFormTabsLayout} style={{ height: '100%', minHeight: 0, flex: 1 }}>
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
      <SynPageBody className={stepFormStyles.nodeFormTabsBody}>
        <Stack hasGutter className={stepFormStyles.nodeFormParametersStack}>
          <StackItem className={stepFormStyles.nodeFormParametersItem}>
            {activeTabKey === 0 ? parametersContent : (settingsContent ?? null)}
          </StackItem>
        </Stack>
      </SynPageBody>
    </Stack>
  )
}
