import { Button, Dropdown, DropdownItem, DropdownList, Icon, MenuToggle, Tooltip } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { EdgeHandleEnum, type SwitchActivity, type SwitchConfig } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import { useCallback, useMemo, useState, type Ref } from 'react'

import { FlowNodeType } from '../../../constants/nodeTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { buildSwitchCasePort } from '../utils/switchCaseHelpers'

import styles from './RightSidePill.module.css'

type BranchHandle = {
  handle: string
  label: string
}

/**
 * Maps branching node types to their output handles.
 * Each handle has a string value (from EdgeHandleEnum) and a human-readable label.
 */
const BRANCHING_HANDLES: Record<string, BranchHandle[]> = {
  [FlowNodeType.CONDITION]: [
    { handle: EdgeHandleEnum.TRUE, label: 'On True' },
    { handle: EdgeHandleEnum.FALSE, label: 'On False' },
  ],
  [FlowNodeType.APPROVAL]: [
    { handle: EdgeHandleEnum.APPROVED, label: 'On Approved' },
    { handle: EdgeHandleEnum.REJECTED, label: 'On Rejected' },
  ],
  [FlowNodeType.LOOP]: [
    { handle: EdgeHandleEnum.LOOP, label: 'In loop' },
    { handle: EdgeHandleEnum.DONE, label: 'On done' },
  ],
}

/**
 * Sanitizes a string for safe display by truncating to a maximum length.
 * Defense-in-depth measure to prevent UI issues from malformed data.
 */
function sanitizeLabel(label: string | undefined, maxLength = 100): string {
  if (!label || typeof label !== 'string') return ''
  return label.slice(0, maxLength)
}

/**
 * Validates that a port value is a safe string identifier.
 * Defense-in-depth measure to prevent injection of unexpected characters.
 */
function isValidPort(port: unknown): port is string {
  return typeof port === 'string' && port.length > 0 && port.length <= 100 && /^[\w-]+$/.test(port)
}

/**
 * Builds branch handles for a switch node based on its case configuration.
 * Returns an array of handles with dynamic path labels from the switch cases,
 * plus a fallback/default handle if configured.
 *
 * Includes runtime validation as defense-in-depth:
 * - Validates node type before type assertion
 * - Sanitizes user-controlled label text
 * - Validates port identifiers
 * - Guards against malformed arrays
 */
function buildSwitchBranchHandles(node: Node<NodeType['data']> | undefined): BranchHandle[] | undefined {
  if (node?.type !== FlowNodeType.SWITCH) return undefined

  // Runtime validation before type assertions
  const nodeData = node.data
  if (!nodeData || typeof nodeData !== 'object') return undefined

  const switchData = nodeData as SwitchActivity
  if (switchData.type !== 'switch') return undefined

  const config = (switchData.parameters ?? { cases: [] }) as SwitchConfig
  const cases = config.cases ?? []

  // Guard against malformed or excessively large arrays (DoS prevention)
  if (!Array.isArray(cases) || cases.length > 50) {
    return undefined
  }

  const caseHandles = cases.map((c, i) => {
    // Validate and sanitize port identifier
    const port = c.port && isValidPort(c.port) ? c.port : buildSwitchCasePort(i)

    // Sanitize user-controlled label text
    const sanitizedLabel = sanitizeLabel(c.label)
    const label = sanitizedLabel ? `On ${sanitizedLabel}` : `On Path ${i + 1}`

    return { handle: port, label }
  })

  // Add fallback/default handle
  const defaultPort =
    config.default_port && isValidPort(config.default_port) ? config.default_port : EdgeHandleEnum.DEFAULT
  const fallbackHandle = [{ handle: defaultPort, label: 'Fallback' }]

  return [...caseHandles, ...fallbackHandle]
}

type RightSidePillProps = {
  node?: Node<NodeType['data']>
  onAddStep?: (handle?: string) => void
}

type AddStepToggleProps = {
  toggleRef: Ref<MenuToggleElement>
  tooltip: string
  isOpen: boolean
  onToggle: () => void
}

function AddStepToggle({ toggleRef, tooltip, isOpen, onToggle }: Readonly<AddStepToggleProps>) {
  return (
    <Tooltip content={tooltip}>
      <MenuToggle
        ref={toggleRef}
        variant="plain"
        className={styles.addStepButton}
        aria-label={tooltip}
        isExpanded={isOpen}
        onClick={onToggle}
      >
        <Icon isInline>
          <RhUiAddIcon />
        </Icon>
      </MenuToggle>
    </Tooltip>
  )
}

type BranchingAddStepProps = {
  handles: BranchHandle[]
  onAddStep: (handle: string) => void
}

function BranchingAddStep({ handles, onAddStep }: Readonly<BranchingAddStepProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const tooltip = 'Add step…'

  const handleSelect = useCallback(
    (handle: string) => {
      onAddStep(handle)
      setIsOpen(false)
    },
    [onAddStep]
  )

  const handleToggleOpen = useCallback(() => setIsOpen((prev) => !prev), [])

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <AddStepToggle toggleRef={toggleRef} tooltip={tooltip} isOpen={isOpen} onToggle={handleToggleOpen} />
    ),
    [tooltip, isOpen, handleToggleOpen]
  )

  return (
    <Dropdown
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      isScrollable
      maxMenuHeight="300px"
      popperProps={{ placement: 'bottom-end' }}
      toggle={renderToggle}
    >
      <DropdownList>
        {handles.map((item) => (
          <DropdownItem key={item.handle} onClick={() => handleSelect(item.handle)}>
            {item.label}
          </DropdownItem>
        ))}
      </DropdownList>
    </Dropdown>
  )
}

type NonBranchingAddStepProps = {
  onAddStep: () => void
}

function NonBranchingAddStep({ onAddStep }: Readonly<NonBranchingAddStepProps>) {
  return (
    <Tooltip content="Add step">
      <Button
        variant="plain"
        type="button"
        className={styles.addStepButton}
        icon={
          <Icon isInline>
            <RhUiAddIcon />
          </Icon>
        }
        aria-label="Add step"
        onClick={onAddStep}
      />
    </Tooltip>
  )
}

export function RightSidePill({ node, onAddStep }: Readonly<RightSidePillProps>) {
  const switchHandles = useMemo(() => buildSwitchBranchHandles(node), [node])

  if (!onAddStep) {
    return null
  }

  const nodeFlowType = node?.type
  const branchHandles =
    switchHandles ?? (nodeFlowType && nodeFlowType in BRANCHING_HANDLES ? BRANCHING_HANDLES[nodeFlowType] : undefined)

  if (branchHandles?.length) {
    return <BranchingAddStep handles={branchHandles} onAddStep={onAddStep} />
  }

  return <NonBranchingAddStep onAddStep={() => onAddStep()} />
}
