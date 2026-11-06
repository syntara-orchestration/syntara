import { StackItem, Tab, Tabs, TabTitleText } from '@patternfly/react-core'

import styles from './NodeExecutionDetailsPanel.module.css'
import { nodeTabPanelId } from './nodeTabPanel'

export function NodeDetailTabBar({
  activeTab,
  onTabChange,
  isAgenticNode,
  idBase,
}: Readonly<{
  activeTab: 'io' | 'agent-steps'
  onTabChange: (tab: 'io' | 'agent-steps') => void
  isAgenticNode: boolean
  /** Base id used to derive stable tab-button ids and the shared panel id, so the tab/panel relationship is exposed to assistive tech. */
  idBase: string
}>) {
  const panelId = nodeTabPanelId(idBase)
  return (
    <StackItem className={styles.tabBar}>
      <Tabs activeKey={activeTab} onSelect={(_e, key) => onTabChange(key as 'io' | 'agent-steps')} variant="default">
        <Tab
          id={`${idBase}-io`}
          tabContentId={panelId}
          eventKey="io"
          title={<TabTitleText>Input/Output</TabTitleText>}
        />
        {isAgenticNode && (
          <Tab
            id={`${idBase}-agent-steps`}
            tabContentId={panelId}
            eventKey="agent-steps"
            title={<TabTitleText>Agent steps</TabTitleText>}
          />
        )}
      </Tabs>
    </StackItem>
  )
}
