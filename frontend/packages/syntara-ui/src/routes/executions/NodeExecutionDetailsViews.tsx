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

import { HelpPopover } from '../../components/expressions/HelpPopover'

import styles from './NodeExecutionDetailsPanel.module.css'

function buildOutputHint(
  outputMode: 'composed' | 'persisted',
  subWorkflowData: Readonly<{ isLoading: boolean; isTruncated: boolean; isError: boolean }>
): string {
  if (outputMode !== 'composed') {
    return 'The stored value used by downstream steps.'
  }
  const notes = [
    subWorkflowData.isLoading ? ' Loading child activities…' : '',
    subWorkflowData.isTruncated ? ' Showing first 100 activities per child.' : '',
    subWorkflowData.isError ? ' Some child activities could not be loaded.' : '',
  ].join('')
  return `Child execution and activity details for inspection — not saved on this step or passed downstream.${notes}`
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
          <ToggleGroup aria-label="Output view" isCompact>
            <ToggleGroupItem
              text="With child data"
              buttonId="sub-wf-output-composed"
              isSelected={outputMode === 'composed'}
              onChange={() => onOutputModeChange('composed')}
            />
            <ToggleGroupItem
              text="Saved output"
              buttonId="sub-wf-output-persisted"
              isSelected={outputMode === 'persisted'}
              onChange={() => onOutputModeChange('persisted')}
            />
          </ToggleGroup>
        </FlexItem>
        <FlexItem>
          <HelpPopover
            ariaLabel="About output views"
            headerContent="About output views"
            bodyContent="With child data adds child execution and activity details for inspection; child activity data is not saved on this step or passed downstream. Saved output shows the stored value used by downstream steps."
          />
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
