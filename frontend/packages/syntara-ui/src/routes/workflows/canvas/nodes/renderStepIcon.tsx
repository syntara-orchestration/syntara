import { Icon } from '@patternfly/react-core'
import type { IconSize } from '@patternfly/react-core'
import type { ComponentType, CSSProperties, ReactNode } from 'react'

import { AAP_STEP_IDS, RegistryStepId } from '../../../../constants'

export type StepIconVariant = 'canvas' | 'list' | 'header' | 'legend'

type VariantConfig = { size: IconSize; iconSize: IconSize; customIconScale: number; customIconOffsetY: number }

/** Scaling config for AAP brand icons (Ansible logo has 1px internal padding in a 38x38 viewBox). */
const aapVariantConfig: Record<StepIconVariant, VariantConfig> = {
  canvas: { size: 'md', iconSize: 'md', customIconScale: 1.8, customIconOffsetY: 0 },
  list: { size: 'xl', iconSize: 'xl', customIconScale: 1.5, customIconOffsetY: 0 },
  header: { size: 'xl', iconSize: 'xl', customIconScale: 1.8, customIconOffsetY: 1 },
  legend: { size: 'md', iconSize: 'md', customIconScale: 1.25, customIconOffsetY: 0 },
}

/** Scaling config for EDA brand icon (logo fills the full 36x36 viewBox edge-to-edge, so needs less scaling). */
const edaVariantConfig: Record<StepIconVariant, VariantConfig> = {
  canvas: { size: 'md', iconSize: 'md', customIconScale: 1.4, customIconOffsetY: 0 },
  list: { size: 'xl', iconSize: 'xl', customIconScale: 1.15, customIconOffsetY: 0 },
  header: { size: 'xl', iconSize: 'xl', customIconScale: 1.4, customIconOffsetY: 0 },
  legend: { size: 'md', iconSize: 'md', customIconScale: 1, customIconOffsetY: 0 },
}

/** Standard PF icon sizing (no custom scaling). */
const standardVariantConfig: Record<StepIconVariant, VariantConfig> = {
  canvas: { size: 'md', iconSize: 'md', customIconScale: 1, customIconOffsetY: 0 },
  list: { size: 'xl', iconSize: 'xl', customIconScale: 1, customIconOffsetY: 0 },
  header: { size: 'xl', iconSize: 'xl', customIconScale: 1, customIconOffsetY: 0 },
  legend: { size: 'md', iconSize: 'md', customIconScale: 1, customIconOffsetY: 0 },
}

function getVariantConfig(nodeId: string | undefined): Record<StepIconVariant, VariantConfig> {
  if (AAP_STEP_IDS.has(nodeId as (typeof RegistryStepId)[keyof typeof RegistryStepId])) {
    return aapVariantConfig
  }
  if (nodeId === RegistryStepId.TRIGGER_EDA) {
    return edaVariantConfig
  }
  return standardVariantConfig
}

export function renderStepIcon(
  IconComponent?: ComponentType,
  nodeId?: string,
  variant: StepIconVariant = 'canvas',
  /** Optional color (e.g. PatternFly token) so icon matches the step type accent; uses currentColor when unset */
  color?: string
): ReactNode | undefined {
  if (!IconComponent) return undefined

  const isAapIcon = AAP_STEP_IDS.has(nodeId as (typeof RegistryStepId)[keyof typeof RegistryStepId])
  const isEdaIcon = nodeId === RegistryStepId.TRIGGER_EDA
  const isCustomIcon = isAapIcon || isEdaIcon
  const shouldRotateIcon = nodeId === RegistryStepId.LOGIC_CONDITION || nodeId === RegistryStepId.LOGIC_CONVERGE
  const { size, iconSize, customIconScale, customIconOffsetY } = getVariantConfig(nodeId)[variant]

  const iconStyle: CSSProperties = {
    ...(shouldRotateIcon && { transform: 'rotate(90deg)' }),
    ...(color && {
      color,
      // Override PatternFly Icon's inner content color so the SVG (fill: currentColor) picks it up
      ['--pf-v6-c-icon__content--Color' as string]: color,
    }),
  }

  return (
    <Icon
      data-testid="step-icon-wrapper"
      size={size}
      iconSize={iconSize}
      style={Object.keys(iconStyle).length > 0 ? iconStyle : undefined}
    >
      {isCustomIcon ? (
        (() => {
          const StyledIcon = IconComponent as ComponentType<{ style?: CSSProperties }>
          return (
            <StyledIcon
              style={{
                width: '100%',
                height: '100%',
                display: 'block',
                transform: `translateY(${customIconOffsetY}px) scale(${customIconScale})`,
                transformOrigin: 'center',
              }}
            />
          )
        })()
      ) : (
        <IconComponent />
      )}
    </Icon>
  )
}
