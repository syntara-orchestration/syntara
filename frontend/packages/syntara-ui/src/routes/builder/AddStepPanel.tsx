import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Icon,
  Spinner,
  Stack,
  StackItem,
  Switch,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiArrowLeftIcon, RhUiAddSquareIcon } from '@patternfly/react-icons'
import { useMemo, useState, type ReactNode } from 'react'

import { SynPanel } from '../../components/layout/SynPanel'
import { useNodeKindsQuery } from '../../hooks/useNodeKindsQuery'

import { StepRegistry } from './registry/StepRegistry'
import { StepTypeOptionsList, type StepTypeOption } from './StepTypeOptionsList'
import {
  filterRestrictedEntries,
  gatePaletteEntries,
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
} from './stepTypePaletteGating'

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

/** Label of the switch that reveals restricted (denied) step types. */
const SHOW_RESTRICTED_STEPS_LABEL = 'Show restricted steps'

function hiddenRestrictedStepsText(count: number): string {
  return count === 1 ? '1 step you cannot add is hidden.' : `${count} steps you cannot add are hidden.`
}

type RestrictedStepsSwitchProps = {
  showRestricted: boolean
  hiddenCount: number
  onChange: (showRestricted: boolean) => void
}

/** Switch that reveals restricted step types padlocked; hidden ones are counted while it is off. */
function RestrictedStepsSwitch({ showRestricted, hiddenCount, onChange }: RestrictedStepsSwitchProps) {
  return (
    <StackItem
      style={{
        paddingLeft: 'var(--pf-t--global--spacer--md)',
        paddingRight: 'var(--pf-t--global--spacer--md)',
        paddingBottom: 'var(--pf-t--global--spacer--md)',
      }}
    >
      <Stack>
        <StackItem>
          <Switch
            id="add-step-show-restricted"
            label={SHOW_RESTRICTED_STEPS_LABEL}
            isChecked={showRestricted}
            onChange={(_event, checked) => onChange(checked)}
          />
        </StackItem>
        {hiddenCount > 0 && (
          <StackItem>
            <Content component={ContentVariants.small} data-testid="add-step-hidden-count">
              {hiddenRestrictedStepsText(hiddenCount)}
            </Content>
          </StackItem>
        )}
      </Stack>
    </StackItem>
  )
}

type AddStepListContentProps = {
  isLoading: boolean
  /** Why every entry is disabled when the panel fails closed, else `null`. */
  failClosedMessage: string | null
  entries: StepTypeOption[]
  hiddenCount: number
  onSelect: (stepTypeId: string) => void
}

function AddStepListContent({ isLoading, failClosedMessage, entries, hiddenCount, onSelect }: AddStepListContentProps) {
  if (isLoading) {
    // First verdict request for this project: a loading state, not a palette
    // that flashes every entry as disabled.
    return (
      <StackItem>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
          <Spinner size="md" aria-label="Checking step permissions" />
          <Content component="p">Checking step permissions…</Content>
        </Flex>
      </StackItem>
    )
  }

  return (
    <>
      {failClosedMessage && (
        <StackItem>
          <Content component={ContentVariants.small} data-testid="add-step-permissions-unavailable">
            {failClosedMessage}
          </Content>
        </StackItem>
      )}
      {entries.length === 0 && hiddenCount > 0 ? (
        <StackItem>
          <Content component="p" data-testid="add-step-all-restricted">
            You cannot add any of these steps. Turn on “{SHOW_RESTRICTED_STEPS_LABEL}” to see them and why.
          </Content>
        </StackItem>
      ) : (
        <StepTypeOptionsList stepTypes={entries} onSelect={onSelect} />
      )}
    </>
  )
}

function sortSubtypes<T extends { order?: number }>(subtypes: readonly T[]): T[] {
  return subtypes
    .map((subtype, index) => ({ subtype, index }))
    .sort((a, b) => (a.subtype.order ?? a.index) - (b.subtype.order ?? b.index))
    .map(({ subtype }) => subtype)
}

type AddStepPanelProps = {
  onClose: () => void
  onSelectStep: (stepTypeId: string, stepSubtypeId?: string | null) => void
  sourceNodeId?: string | null
  /** Canvas has no workflow steps yet (only trigger selection is shown). */
  hasNoWorkflowSteps?: boolean
  /** React Flow node ID to replace (generic placeholder → real step). */
  replacementNodeId?: string | null
  /** Project whose step-type denies the palette reflects (R18). */
  projectId?: string | null
}

export function AddStepPanel(props: AddStepPanelProps) {
  const [selectedStepType, setSelectedStepType] = useState<string | null>(null)
  const [showRestricted, setShowRestricted] = useState(false)
  const { nodeKindByKind, isLoading, isUnavailable } = useNodeKindsQuery(props.projectId)

  // Registered step types from StepRegistry
  // Omit triggers when adding from an edge (sourceNodeId) or replacing a generic step (replacementNodeId)
  // because triggers cannot be connection targets
  const registeredStepTypes = useMemo(() => {
    const allSteps = StepRegistry.getAll()
    if (props.hasNoWorkflowSteps) {
      return allSteps.filter((step) => step.category === 'trigger')
    }
    if (props.sourceNodeId || props.replacementNodeId) {
      return allSteps.filter((step) => step.category !== 'trigger')
    }
    return allSteps
  }, [props.replacementNodeId, props.hasNoWorkflowSteps, props.sourceNodeId])

  // Step-type denies are evaluated per project. Without one the verdicts are
  // unknown, so the panel fails closed like an unavailable endpoint instead of
  // claiming everything is allowed. The server still rejects the save.
  const isMissingProject = !props.projectId
  const isFailClosed = isUnavailable || isMissingProject
  const failClosedMessage = isMissingProject ? STEP_TYPE_NO_PROJECT_TOOLTIP : STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP

  // Step types the caller may not author are hidden by default; the switch
  // reveals them padlocked and inert, with a tooltip naming the blocking
  // policy. Steps already on the canvas are unaffected.
  const stepTypes = useMemo(
    () => gatePaletteEntries(registeredStepTypes, nodeKindByKind, isFailClosed, failClosedMessage),
    [registeredStepTypes, nodeKindByKind, isFailClosed, failClosedMessage]
  )

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
  const gatedSubtypes = gatePaletteEntries(
    sortSubtypes(selectedStep?.subtypes ?? []),
    nodeKindByKind,
    isFailClosed,
    failClosedMessage
  )

  // When failing closed every entry is restricted: hiding them all would leave
  // an empty palette, so they stay listed, disabled, with an explanation.
  const currentEntries: StepTypeOption[] = isShowingSubtypeList ? gatedSubtypes : stepTypes
  const { entries: visibleEntries, restrictedCount } = filterRestrictedEntries(
    currentEntries,
    isFailClosed || showRestricted
  )
  const hiddenCount = showRestricted ? 0 : restrictedCount
  const hasRestrictionSwitch = !isLoading && !isFailClosed && restrictedCount > 0

  const handleSubtypeClick = (subtypeId: string) => {
    if (!selectedStep) return
    props.onSelectStep(selectedStep.id, subtypeId)
    setSelectedStepType(null)
  }

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
        {hasRestrictionSwitch && (
          <RestrictedStepsSwitch
            showRestricted={showRestricted}
            hiddenCount={hiddenCount}
            onChange={setShowRestricted}
          />
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
          <Stack hasGutter>
            <AddStepListContent
              isLoading={isLoading}
              failClosedMessage={isFailClosed ? failClosedMessage : null}
              entries={visibleEntries}
              hiddenCount={hiddenCount}
              onSelect={isShowingSubtypeList ? handleSubtypeClick : handleStepClick}
            />
          </Stack>
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
