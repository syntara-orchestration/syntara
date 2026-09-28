import {
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Label,
  Split,
  SplitItem,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'

import { SynPanel } from '../../components/layout/SynPanel'
import { AAP_NODE_IDS, RegistryNodeId } from '../../constants'
import { renderNodeIcon } from '../workflows/canvas/nodes/renderNodeIcon'
import { getAddNodePanelColor } from '../workflows/canvas/nodeTypeColors'

import type { NodeSubtypeDefinition, NodeTypeDefinition } from './registry/NodeRegistry'
import { resolveIconForType } from './utils/nodeIcons'

export type NodeTypeOption = Pick<NodeTypeDefinition | NodeSubtypeDefinition, 'id' | 'label' | 'icon' | 'description'>

type NodeTypeOptionsListProps = {
  nodeTypes: NodeTypeOption[]
  onSelect: (nodeId: string) => void
}

export function NodeTypeOptionsList(props: NodeTypeOptionsListProps) {
  return props.nodeTypes.map((nodeType) => {
    const { icon, id } = resolveIconForType({ nodeTypeId: nodeType.id })
    const accentColor = getAddNodePanelColor(nodeType.id)
    // AAP nodes use gray icon (no color tint)
    const isAAPNode = AAP_NODE_IDS.has(nodeType.id as (typeof RegistryNodeId)[keyof typeof RegistryNodeId])
    const iconColor = isAAPNode ? undefined : accentColor
    const nodeIcon = renderNodeIcon(icon, id, 'list', iconColor)

    return (
      <StackItem key={nodeType.id}>
        <SynPanel
          isGlass={false}
          isScrollable={false}
          onClick={() => props.onSelect(nodeType.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              props.onSelect(nodeType.id)
            }
          }}
          style={{
            cursor: 'pointer',
            ...(accentColor
              ? {
                  borderTopWidth: 4,
                  borderTopStyle: 'solid',
                  borderTopColor: accentColor,
                  borderRightWidth: 0,
                  borderBottomWidth: 0,
                  borderLeftWidth: 0,
                }
              : {}),
          }}
          role="button"
          tabIndex={0}
          aria-label={nodeType.label}
        >
          <Stack hasGutter>
            <StackItem>
              <Split hasGutter>
                <SplitItem isFilled={false} style={{ width: '2rem', flexShrink: 0 }}>
                  {nodeIcon}
                </SplitItem>
                <SplitItem isFilled>
                  <Flex
                    alignItems={{ default: 'alignItemsCenter' }}
                    gap={{ default: 'gapSm' }}
                    flexWrap={{ default: 'nowrap' }}
                  >
                    <FlexItem flex={{ default: 'flexNone' }}>
                      <Title headingLevel="h3" size="md">
                        {nodeType.label}
                      </Title>
                    </FlexItem>
                    {nodeType.id === RegistryNodeId.ACTION_SCRIPT && (
                      <FlexItem>
                        <Label isCompact color="orange" style={{ fontSize: 'var(--pf-t--global--font--size--sm)' }}>
                          Developer Preview
                        </Label>
                      </FlexItem>
                    )}
                  </Flex>
                </SplitItem>
              </Split>
            </StackItem>
            <StackItem>
              {nodeType.description && (
                <Content data-testid="node-type-description" component={ContentVariants.small}>
                  {nodeType.description}
                </Content>
              )}
            </StackItem>
          </Stack>
        </SynPanel>
      </StackItem>
    )
  })
}
