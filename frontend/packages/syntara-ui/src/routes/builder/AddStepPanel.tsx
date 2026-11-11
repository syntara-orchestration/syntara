import { Button, Flex, FlexItem, Icon, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiArrowLeftIcon, RhUiAddSquareIcon } from '@patternfly/react-icons'
import { useMemo, useState, type ReactNode } from 'react'

import { SynPanel } from '../../components/layout/SynPanel'

import { StepRegistry } from './registry/StepRegistry'
import { StepTypeOptionsList } from './StepTypeOptionsList'

type AddStepPanelHeaderProps = {
  panelTitle: string
  isShowingSubtypeList: boolean
  hasNoWorkflowSteps?: boolean
  onBack: () => void
  onClose: () => void
}

export function AddStepPanelHeader({
  panelTitle,
  isShowingSubtypeList,
  hasNoWorkflowSteps,
  onBack,
  onClose,
}: AddStepPanelHeaderProps) {
  let leadingControl: ReactNode = null
  if (isShowingSubtypeList && !hasNoWorkflowSteps) {
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
        {!hasNoWorkflowSteps && (
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

type AddStepPanelProps = {
  onClose: () => void
  onSelectStep: (stepTypeId: string, stepSubtypeId?: string | null) => void
  sourceNodeId?: string | null
  /** Canvas has no workflow steps yet (only trigger selection is shown). */
  hasNoWorkflowSteps?: boolean
  /** React Flow node ID to replace (generic placeholder → real step). */
  replacementNodeId?: string | null
}

export function AddStepPanel(props: AddStepPanelProps) {
  const [selectedStepType, setSelectedStepType] = useState<string | null>(null)

  // Registered step types from StepRegistry
  // Omit triggers when adding from an edge (sourceNodeId) or replacing a generic step (replacementNodeId)
  // because triggers cannot be connection targets
  const stepTypes = useMemo(() => {
    const allSteps = StepRegistry.getAll()
    if (props.hasNoWorkflowSteps) {
      return allSteps.filter((step) => step.category === 'trigger')
    }
    if (props.sourceNodeId || props.replacementNodeId) {
      return allSteps.filter((step) => step.category !== 'trigger')
    }
    return allSteps
  }, [props.replacementNodeId, props.hasNoWorkflowSteps, props.sourceNodeId])

  const handleStepClick = (stepTypeId: string) => {
    const stepDefinition = StepRegistry.get(stepTypeId)
    if (stepDefinition?.subtypes?.length) {
      setSelectedStepType(stepTypeId)
      return
    }
    props.onSelectStep(stepTypeId, null)
    setSelectedStepType(null)
  }

  // Selected step type definition (may show subtype list)
  const enforcedSelectedStepType = props.hasNoWorkflowSteps ? 'trigger' : selectedStepType
  const selectedStep = enforcedSelectedStepType ? StepRegistry.get(enforcedSelectedStepType) : null
  const isShowingSubtypeList = !!selectedStep?.subtypes?.length

  const panelTitle =
    isShowingSubtypeList && selectedStep ? (selectedStep.selectionTitle ?? 'Select a step') : 'Add step'

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
        <AddStepPanelHeader
          panelTitle={panelTitle}
          isShowingSubtypeList={isShowingSubtypeList}
          hasNoWorkflowSteps={props.hasNoWorkflowSteps}
          onBack={() => setSelectedStepType(null)}
          onClose={props.onClose}
        />
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
          <Stack hasGutter>
            {selectedStep?.subtypes?.length ? (
              <StepTypeOptionsList
                stepTypes={selectedStep.subtypes
                  .map((subtype, index) => ({ subtype, index }))
                  .sort((a, b) => (a.subtype.order ?? a.index) - (b.subtype.order ?? b.index))
                  .map(({ subtype }) => subtype)}
                onSelect={(subtypeId) => {
                  props.onSelectStep(selectedStep.id, subtypeId)
                  setSelectedStepType(null)
                }}
              />
            ) : (
              <StepTypeOptionsList stepTypes={stepTypes} onSelect={handleStepClick} />
            )}
          </Stack>
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
