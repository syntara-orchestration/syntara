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
import { AAP_STEP_IDS, RegistryStepId } from '../../constants'
import { renderStepIcon } from '../workflows/canvas/nodes/renderStepIcon'
import { getAddStepPanelColor } from '../workflows/canvas/stepTypeColors'

import type { StepSubtypeDefinition, StepTypeDefinition } from './registry/StepRegistry'
import { resolveIconForType } from './utils/stepIcons'

export type StepTypeOption = Pick<StepTypeDefinition | StepSubtypeDefinition, 'id' | 'label' | 'icon' | 'description'>

type StepTypeOptionsListProps = {
  stepTypes: StepTypeOption[]
  onSelect: (stepTypeId: string) => void
}

export function StepTypeOptionsList(props: StepTypeOptionsListProps) {
  return props.stepTypes.map((stepType) => {
    const { icon, id } = resolveIconForType({ stepTypeId: stepType.id })
    const accentColor = getAddStepPanelColor(stepType.id)
    // AAP steps use gray icons (no color tint)
    const isAAPStep = AAP_STEP_IDS.has(stepType.id as (typeof RegistryStepId)[keyof typeof RegistryStepId])
    const iconColor = isAAPStep ? undefined : accentColor
    const stepIcon = renderStepIcon(icon, id, 'list', iconColor)

    return (
      <StackItem key={stepType.id}>
        <SynPanel
          isGlass={false}
          isScrollable={false}
          onClick={() => props.onSelect(stepType.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              props.onSelect(stepType.id)
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
          aria-label={stepType.label}
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
      </StackItem>
    )
  })
}
