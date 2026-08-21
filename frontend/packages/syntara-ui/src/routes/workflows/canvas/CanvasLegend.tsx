import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Icon,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import {
  RhUiInformationIcon,
  RhUiBranchFillIcon,
  RhUiCloseIcon,
  RhUiElectricityFillIcon,
  RhUiPlayIcon,
  RhUiRobotIcon,
  RhUiUserCheckIcon,
} from '@patternfly/react-icons'
import { type ComponentType, type CSSProperties } from 'react'

import AnsibleIcon from '../../../assets/ansible-automation-platform.svg?react'
import { SynPanel } from '../../../components/layout/SynPanel'
import { AAP_NODE_IDS, RegistryNodeId } from '../../../constants'

import { APPROVAL_BRANCH_TOKENS } from './nodes/common/approvalBranchTokens'
import { renderNodeIcon } from './nodes/renderNodeIcon'
import { getAddNodePanelColor } from './nodeTypeColors'

/** Subsection titles: lighter than legend row labels (mock: standard weight). */
const LEGEND_SECTION_HEADING_STYLE: CSSProperties = {
  fontSize: 'var(--pf-t--global--font--size--body--sm)',
  fontWeight: 'var(--pf-t--global--font--weight--body--default)',
  margin: 0,
}

/** Row labels: stronger than section headers (mock: heavier body / near-heading). */
const LEGEND_ROW_LABEL_STYLE: CSSProperties = {
  fontWeight: 'var(--pf-t--global--font--weight--heading--default)',
}

/** Matches `renderNodeIcon` `legend` variant (`Icon` `md` = global icon size md). */
const LEGEND_ROW_GLYPH_SIZE = 'var(--pf-t--global--icon--size--md)'

/** Fixed column so legend labels share a common start edge (icons/swatches centered in column). */
const LEGEND_GLYPH_COLUMN_STYLE: CSSProperties = {
  width: '2.25rem',
  minWidth: '2.25rem',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  flexShrink: 0,
}

function legendIconColor(registryNodeId: string): string | undefined {
  if (AAP_NODE_IDS.has(registryNodeId as (typeof RegistryNodeId)[keyof typeof RegistryNodeId])) {
    return undefined
  }
  return getAddNodePanelColor(registryNodeId)
}

const LEGEND_ROWS: ReadonlyArray<{
  label: string
  icon: ComponentType<{ className?: string }>
  registryId: string
}> = [
  {
    label: 'Task Agent',
    icon: RhUiRobotIcon,
    registryId: RegistryNodeId.AGENT,
  },
  {
    label: 'Action',
    icon: RhUiElectricityFillIcon,
    registryId: RegistryNodeId.ACTION,
  },
  {
    label: 'AAP execution',
    icon: AnsibleIcon as ComponentType<{ className?: string }>,
    registryId: RegistryNodeId.AAP_EXECUTION,
  },
  {
    label: 'Logic',
    icon: RhUiBranchFillIcon,
    registryId: RegistryNodeId.LOGIC,
  },
  {
    label: 'Approval',
    icon: RhUiUserCheckIcon,
    registryId: RegistryNodeId.APPROVAL,
  },
  {
    label: 'Trigger',
    icon: RhUiPlayIcon,
    registryId: RegistryNodeId.TRIGGER,
  },
]

function ApprovalBranchLegendSwatch(props: Readonly<{ variant: 'approved' | 'rejected'; label: string }>) {
  const t = props.variant === 'approved' ? APPROVAL_BRANCH_TOKENS.approved : APPROVAL_BRANCH_TOKENS.rejected
  return (
    <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem style={LEGEND_GLYPH_COLUMN_STYLE}>
        <span
          aria-hidden
          style={{
            width: LEGEND_ROW_GLYPH_SIZE,
            height: LEGEND_ROW_GLYPH_SIZE,
            borderRadius: '50%',
            backgroundColor: t.backgroundColor,
            border: `2px solid ${t.borderColor}`,
            flexShrink: 0,
            boxSizing: 'border-box',
          }}
        />
      </FlexItem>
      <Content component={ContentVariants.small} style={LEGEND_ROW_LABEL_STYLE}>
        {props.label}
      </Content>
    </Flex>
  )
}

export type CanvasLegendProps = Readonly<{
  /** Stable id for `aria-controls` on the toolbar trigger and section `aria-labelledby` hooks. */
  regionId: string
  /** Popover internal hide; invoke before `onClose` when dismissing from inside the popover. */
  hide: () => void
  /** Parent close handler (state + focus return). */
  onClose: () => void
}>

function CanvasLegendHeader(props: Readonly<{ regionId: string; hide: () => void; onClose: () => void }>) {
  const titleId = `${props.regionId}-legend-title`
  const close = () => {
    props.hide()
    props.onClose()
  }
  return (
    <Flex
      justifyContent={{ default: 'justifyContentSpaceBetween' }}
      alignItems={{ default: 'alignItemsCenter' }}
      flexWrap={{ default: 'nowrap' }}
    >
      <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }} style={{ flex: 1, minWidth: 0 }}>
        <Icon isInline size="lg" iconSize="lg">
          <RhUiInformationIcon />
        </Icon>
        <Title headingLevel="h2" size={TitleSizes.lg} id={titleId}>
          Legend
        </Title>
      </Flex>
      <FlexItem>
        <Button
          variant="plain"
          aria-label="Close legend"
          onClick={close}
          icon={
            <Icon isInline>
              <RhUiCloseIcon />
            </Icon>
          }
        />
      </FlexItem>
    </Flex>
  )
}

export function CanvasLegend(props: CanvasLegendProps) {
  return (
    <div id={props.regionId}>
      <SynPanel
        data-testid="canvas-legend"
        variant="raised"
        panelMainBodyProps={{ style: { padding: 'var(--pf-t--global--spacer--lg)' } }}
      >
        <CanvasLegendHeader regionId={props.regionId} hide={props.hide} onClose={props.onClose} />
        <Stack
          component="section"
          hasGutter
          aria-labelledby={`${props.regionId}-steps-heading`}
          style={{ marginTop: 'var(--pf-t--global--spacer--md)' }}
        >
          <StackItem>
            <Content component="h3" id={`${props.regionId}-steps-heading`} style={LEGEND_SECTION_HEADING_STYLE}>
              Steps
            </Content>
          </StackItem>
          {LEGEND_ROWS.map((row) => (
            <StackItem key={row.registryId}>
              <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                <FlexItem style={LEGEND_GLYPH_COLUMN_STYLE}>
                  {renderNodeIcon(row.icon, row.registryId, 'legend', legendIconColor(row.registryId))}
                </FlexItem>
                <Content component={ContentVariants.small} style={LEGEND_ROW_LABEL_STYLE}>
                  {row.label}
                </Content>
              </Flex>
            </StackItem>
          ))}
        </Stack>
        <Stack
          component="section"
          hasGutter
          aria-labelledby={`${props.regionId}-connectors-heading`}
          style={{ marginTop: 'var(--pf-t--global--spacer--lg)' }}
        >
          <StackItem>
            <Content component="h3" id={`${props.regionId}-connectors-heading`} style={LEGEND_SECTION_HEADING_STYLE}>
              Connectors
            </Content>
          </StackItem>
          <StackItem>
            <ApprovalBranchLegendSwatch variant="approved" label="Approved" />
          </StackItem>
          <StackItem>
            <ApprovalBranchLegendSwatch variant="rejected" label="Rejected" />
          </StackItem>
        </Stack>
      </SynPanel>
    </div>
  )
}
