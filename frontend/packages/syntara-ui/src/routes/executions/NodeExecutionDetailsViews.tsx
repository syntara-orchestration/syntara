import {
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  StackItem,
  Tab,
  Tabs,
  TabTitleText,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'

import styles from './NodeExecutionDetailsPanel.module.css'

function buildOutputHint(
  outputMode: 'composed' | 'persisted',
  subWorkflowData: Readonly<{ isLoading: boolean; isTruncated: boolean; isError: boolean }>
): string {
  if (outputMode !== 'composed') {
    return 'The exact value persisted on this node and available to downstream steps.'
  }
  const notes = [
    subWorkflowData.isLoading ? ' Loading child activities…' : '',
    subWorkflowData.isTruncated ? ' Showing first 100 activities per child.' : '',
    subWorkflowData.isError ? ' Some child activities could not be loaded.' : '',
  ].join('')
  return `child_activities are composed from the child execution for inspection — not stored on this node's output.${notes}`
}

export function SubWorkflowOutputView({
  outputMode,
  onOutputModeChange,
  subWorkflowData,
}: Readonly<{
  outputMode: 'composed' | 'persisted'
  onOutputModeChange: (mode: 'composed' | 'persisted') => void
  subWorkflowData: Readonly<{ isLoading: boolean; isTruncated: boolean; isError: boolean }>
}>) {
  return (
    <StackItem style={{ flexShrink: 0, paddingBottom: 'var(--pf-t--global--spacer--sm)' }}>
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
        <FlexItem>
          <Content component={ContentVariants.small} style={{ margin: 0 }}>
            Output view:
          </Content>
        </FlexItem>
        <FlexItem>
          <ToggleGroup aria-label="Output view">
            <ToggleGroupItem
              text="Composed"
              buttonId="sub-wf-output-composed"
              isSelected={outputMode === 'composed'}
              onChange={() => onOutputModeChange('composed')}
            />
            <ToggleGroupItem
              text="Persisted"
              buttonId="sub-wf-output-persisted"
              isSelected={outputMode === 'persisted'}
              onChange={() => onOutputModeChange('persisted')}
            />
          </ToggleGroup>
        </FlexItem>
        <FlexItem flex={{ default: 'flex_1' }}>
          <Content
            component={ContentVariants.small}
            style={{ margin: 0, color: 'var(--pf-t--global--text--color--subtle)' }}
          >
            {buildOutputHint(outputMode, subWorkflowData)}
          </Content>
        </FlexItem>
      </Flex>
    </StackItem>
  )
}

export function NodeDetailTabBar({
  activeTab,
  onTabChange,
  isAgenticNode,
  isSubWorkflowNode,
}: Readonly<{
  activeTab: 'io' | 'agent-steps' | 'child-activities'
  onTabChange: (tab: 'io' | 'agent-steps' | 'child-activities') => void
  isAgenticNode: boolean
  isSubWorkflowNode: boolean
}>) {
  return (
    <StackItem className={styles.tabBar}>
      <Tabs
        activeKey={activeTab}
        onSelect={(_e, key) => onTabChange(key as 'io' | 'agent-steps' | 'child-activities')}
        variant="default"
      >
        <Tab eventKey="io" title={<TabTitleText>Input/Output</TabTitleText>} />
        {isAgenticNode && <Tab eventKey="agent-steps" title={<TabTitleText>Agent steps</TabTitleText>} />}
        {isSubWorkflowNode && <Tab eventKey="child-activities" title={<TabTitleText>Child activities</TabTitleText>} />}
      </Tabs>
    </StackItem>
  )
}
