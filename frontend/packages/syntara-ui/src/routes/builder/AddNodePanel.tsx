import { Button, Flex, FlexItem, Icon, SearchInput, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiArrowLeftIcon, RhUiAddSquareIcon } from '@patternfly/react-icons'
import { useMemo, useState, type ReactNode } from 'react'

import { SynPanel } from '../../components/layout/SynPanel'
import { RegistryNodeId } from '../../constants'

import { collectCatalogMatches, filterNodeOptions } from './filterNodeOptions'
import { NodeTypeOptionsList } from './NodeTypeOptionsList'
import { NodeRegistry } from './registry/NodeRegistry'

type AddNodePanelHeaderProps = {
  panelTitle: string
  isShowingSubtypeList: boolean
  hasNoWorkflowNodes?: boolean
  onBack: () => void
  onClose: () => void
}

export function AddNodePanelHeader({
  panelTitle,
  isShowingSubtypeList,
  hasNoWorkflowNodes,
  onBack,
  onClose,
}: AddNodePanelHeaderProps) {
  let leadingControl: ReactNode = null
  if (isShowingSubtypeList && !hasNoWorkflowNodes) {
    leadingControl = (
      <Button variant="plain" onClick={onBack} aria-label="Back">
        <Icon>
          <RhUiArrowLeftIcon />
        </Icon>
      </Button>
    )
  } else if (!isShowingSubtypeList) {
    leadingControl = (
      <Icon>
        <RhUiAddSquareIcon />
      </Icon>
    )
  }

  return (
    <StackItem>
      <Flex
        alignItems={{ default: 'alignItemsCenter' }}
        gap={{ default: 'gapSm' }}
        style={{ padding: 'var(--pf-t--global--spacer--md)' }}
      >
        <FlexItem flex={{ default: 'flex_1' }}>
          <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem>{leadingControl}</FlexItem>
            <FlexItem flex={{ default: 'flex_1' }}>
              <Title headingLevel="h2" size={TitleSizes.lg}>
                {panelTitle}
              </Title>
            </FlexItem>
          </Flex>
        </FlexItem>
        {!hasNoWorkflowNodes && (
          <FlexItem>
            <Button variant="plain" onClick={onClose} aria-label="Close add step panel">
              <Icon>
                <RhUiCloseIcon />
              </Icon>
            </Button>
          </FlexItem>
        )}
      </Flex>
    </StackItem>
  )
}

type AddNodePanelProps = {
  onClose: () => void
  onSelectNode: (nodeTypeId: string, nodeSubtypeId?: string | null) => void
  sourceNodeId?: string | null
  /** Canvas has no workflow steps yet (only trigger selection is shown). */
  hasNoWorkflowNodes?: boolean
  /** React Flow node ID to replace (generic placeholder → real step). */
  replacementNodeId?: string | null
}

export function AddNodePanel(props: AddNodePanelProps) {
  const [selectedNodeType, setSelectedNodeType] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Registered step types from NodeRegistry
  // Omit triggers when adding from an edge (sourceNodeId) or replacing a generic step (replacementNodeId)
  // because triggers cannot be connection targets
  const nodeTypes = useMemo(() => {
    const allNodes = NodeRegistry.getAll()
    if (props.hasNoWorkflowNodes) {
      return allNodes.filter((node) => node.category === 'trigger')
    }
    if (props.sourceNodeId || props.replacementNodeId) {
      return allNodes.filter((node) => node.category !== 'trigger')
    }
    return allNodes
  }, [props.replacementNodeId, props.hasNoWorkflowNodes, props.sourceNodeId])

  const handleNodeClick = (nodeId: string) => {
    const nodeDef = NodeRegistry.get(nodeId)
    if (nodeDef?.subtypes?.length) {
      setSearchQuery('')
      setSelectedNodeType(nodeId)
      return
    }
    props.onSelectNode(nodeId, null)
    setSelectedNodeType(null)
  }

  const handleBack = () => {
    setSearchQuery('')
    setSelectedNodeType(null)
  }

  // Selected step type definition (may show subtype list)
  const enforcedSelectedNodeType = props.hasNoWorkflowNodes ? 'trigger' : selectedNodeType
  const selectedNode = enforcedSelectedNodeType ? NodeRegistry.get(enforcedSelectedNodeType) : null
  const isShowingSubtypeList = !!selectedNode?.subtypes?.length

  const panelTitle =
    isShowingSubtypeList && selectedNode ? (selectedNode.selectionTitle ?? 'Select a node') : 'Add step'

  const subtypeOptions = useMemo(() => {
    if (!selectedNode?.subtypes?.length) return []
    return [...selectedNode.subtypes]
      .map((subtype, index) => ({ subtype, index }))
      .sort((a, b) => (a.subtype.order ?? a.index) - (b.subtype.order ?? b.index))
      .map(({ subtype }) => subtype)
  }, [selectedNode])

  const catalogMatches = useMemo(
    () => (isShowingSubtypeList ? [] : collectCatalogMatches(nodeTypes, searchQuery)),
    [isShowingSubtypeList, nodeTypes, searchQuery]
  )
  const visibleSubtypeOptions = useMemo(
    () => (isShowingSubtypeList ? filterNodeOptions(subtypeOptions, searchQuery) : []),
    [isShowingSubtypeList, searchQuery, subtypeOptions]
  )
  const hasResults = isShowingSubtypeList ? visibleSubtypeOptions.length > 0 : catalogMatches.length > 0
  const showSearch = !props.hasNoWorkflowNodes

  const searchPlaceholder = selectedNode?.id === RegistryNodeId.TERRAFORM ? 'Search actions...' : 'Search...'

  const handleCatalogSelect = (nodeId: string) => {
    const match = catalogMatches.find((item) => item.option.id === nodeId)
    if (match?.subtypeId) {
      props.onSelectNode(match.parentId, match.subtypeId)
      setSearchQuery('')
      setSelectedNodeType(null)
      return
    }
    handleNodeClick(nodeId)
  }

  let optionsList: ReactNode = (
    <NodeTypeOptionsList nodeTypes={catalogMatches.map((match) => match.option)} onSelect={handleCatalogSelect} />
  )
  if (!hasResults) {
    optionsList = (
      <StackItem>
        <Title headingLevel="h3" size={TitleSizes.md}>
          No results found
        </Title>
      </StackItem>
    )
  } else if (selectedNode?.subtypes?.length) {
    optionsList = (
      <NodeTypeOptionsList
        nodeTypes={visibleSubtypeOptions}
        onSelect={(subtypeId) => {
          props.onSelectNode(selectedNode.id, subtypeId)
          setSelectedNodeType(null)
        }}
      />
    )
  }

  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      isGlass={false}
      role="region"
      aria-label={panelTitle}
      style={{
        height: '100%',
        maxHeight: '100%',
        width: '20rem',
        flexShrink: 0,
      }}
    >
      <Stack style={{ flex: 1, minHeight: 0, height: '100%', overflow: 'hidden' }}>
        <AddNodePanelHeader
          panelTitle={panelTitle}
          isShowingSubtypeList={isShowingSubtypeList}
          hasNoWorkflowNodes={props.hasNoWorkflowNodes}
          onBack={handleBack}
          onClose={props.onClose}
        />
        {showSearch && (
          <StackItem
            style={{
              paddingLeft: 'var(--pf-t--global--spacer--md)',
              paddingRight: 'var(--pf-t--global--spacer--md)',
              paddingBottom: 'var(--pf-t--global--spacer--sm)',
            }}
          >
            <SearchInput
              aria-label={searchPlaceholder}
              placeholder={searchPlaceholder}
              value={searchQuery}
              onChange={(_event, value) => setSearchQuery(value)}
              onClear={() => setSearchQuery('')}
            />
          </StackItem>
        )}
        <StackItem
          isFilled
          style={{
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'hidden',
            paddingLeft: 'var(--pf-t--global--spacer--md)',
            paddingRight: 'var(--pf-t--global--spacer--md)',
            paddingBottom: 'var(--pf-t--global--spacer--md)',
          }}
        >
          <Stack hasGutter>{optionsList}</Stack>
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
