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

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynPanel } from '../../components/layout/SynPanel'
import { AAP_STEP_IDS, RegistryStepId } from '../../constants'
import { renderStepIcon } from '../workflows/canvas/nodes/renderStepIcon'
import { getAddStepPanelColor } from '../workflows/canvas/stepTypeColors'

import type { StepSubtypeDefinition, StepTypeDefinition } from './registry/StepRegistry'
import { resolveIconForType } from './utils/stepIcons'

export type StepTypeOption = Pick<
  StepTypeDefinition | StepSubtypeDefinition,
  'id' | 'label' | 'icon' | 'description'
> & {
  /** Entry stays listed but cannot be added (for example a blocked step type). */
  isDisabled?: boolean
  /** Explains why the entry is disabled; shown in a tooltip on hover and focus. */
  disabledTooltip?: string
}

type StepTypeOptionsListProps = {
  stepTypes: StepTypeOption[]
  onSelect: (stepTypeId: string) => void
}

export function StepTypeOptionsList(props: StepTypeOptionsListProps) {
  return props.stepTypes.map((stepType) => {
    const isDisabled = stepType.isDisabled === true
    const { icon, id } = resolveIconForType({ stepTypeId: stepType.id })
    const accentColor = getAddStepPanelColor(stepType.id)
    // AAP steps use gray icon (no color tint)
    const isAAPStep = AAP_STEP_IDS.has(stepType.id as (typeof RegistryStepId)[keyof typeof RegistryStepId])
    const iconColor = isAAPStep ? undefined : accentColor
    const stepIcon = renderStepIcon(icon, id, 'list', iconColor)

    return (
      <StackItem key={stepType.id}>
        <DisabledWithTooltip isDisabled={isDisabled} content={stepType.disabledTooltip ?? ''} position="left">
          <SynPanel
            isGlass={false}
            isScrollable={false}
            onClick={isDisabled ? undefined : () => props.onSelect(stepType.id)}
            onKeyDown={(e) => {
              if (isDisabled) return
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                props.onSelect(stepType.id)
              }
            }}
            style={{
              cursor: isDisabled ? 'not-allowed' : 'pointer',
              ...(isDisabled ? { opacity: 0.5 } : {}),
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
            aria-label={stepType.label}
            aria-disabled={isDisabled || undefined}
          >
            <Stack hasGutter>
              <StackItem>
                <Split hasGutter>
                  <SplitItem isFilled={false} style={{ width: '2rem', flexShrink: 0 }}>
                    {stepIcon}
                  </SplitItem>
                  <SplitItem isFilled>
                    <Flex
                      alignItems={{ default: 'alignItemsCenter' }}
                      gap={{ default: 'gapSm' }}
                      flexWrap={{ default: 'nowrap' }}
                    >
                      <FlexItem flex={{ default: 'flexNone' }}>
                        <Title headingLevel="h3" size="md">
                          {stepType.label}
                        </Title>
                      </FlexItem>
                      {stepType.id === RegistryStepId.ACTION_SCRIPT && (
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
                {stepType.description && (
                  <Content data-testid="step-type-description" component={ContentVariants.small}>
                    {stepType.description}
                  </Content>
                )}
              </StackItem>
            </Stack>
          </SynPanel>
        </DisabledWithTooltip>
      </StackItem>
    )
  })
}
