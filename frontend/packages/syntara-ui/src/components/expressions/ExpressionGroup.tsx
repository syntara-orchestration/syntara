/**
 * Group component for the expression builder
 * Renders a group of conditions/groups with logical operator (AND/OR)
 * Supports recursive nesting
 */

import {
  Button,
  Checkbox,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  List,
  ListItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  FormGroup,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import React, { useCallback, useState } from 'react'

import { createDefaultCondition, createDefaultGroup } from '../../utils/expressions/defaults'
import type {
  ExpressionGroup as ExpressionGroupType,
  ExpressionNode,
  LogicalOperator,
} from '../../utils/expressions/types'
import { SynSelect } from '../SynSelect'

import { ExpressionCondition } from './ExpressionCondition'
import { HelpPopover } from './HelpPopover'

const GroupHelp = () => (
  <HelpPopover
    ariaLabel="Group help"
    headerContent="Group"
    bodyContent={
      <Content component={ContentVariants.p}>
        A container for nested logic. Groups allow you to create complex "If/Then" scenarios, such as: (Condition A AND
        Condition B) OR (Condition C).
      </Content>
    }
  />
)

const RuleHelp = () => (
  <HelpPopover
    ariaLabel="Rule help"
    headerContent="Rule"
    bodyContent={
      <Content>
        <Content component={ContentVariants.p}>
          Define the relationship between your top-level conditions and groups.
        </Content>
        <List>
          <ListItem>
            <strong>AND:</strong> All conditions/groups must be true to proceed.
          </ListItem>
          <ListItem>
            <strong>OR:</strong> Only one condition/group needs to be true to proceed.
          </ListItem>
        </List>
      </Content>
    }
  />
)

const GroupRuleHelp = () => (
  <HelpPopover
    ariaLabel="Group rule help"
    headerContent="Group rule"
    bodyContent={
      <Content>
        <Content component={ContentVariants.p}>Determine the logic for this specific subset of conditions.</Content>
        <List>
          <ListItem>
            <strong>AND:</strong> Every condition inside this nested group must be true.
          </ListItem>
          <ListItem>
            <strong>OR:</strong> If any single condition inside this group is true, the entire group evaluates as true.
          </ListItem>
        </List>
      </Content>
    }
  />
)

const GroupNotHelp = () => (
  <HelpPopover
    ariaLabel="Group NOT operator help"
    headerContent="Not"
    bodyContent={
      <Content component={ContentVariants.p}>
        Inverse the logic of this entire group. When checked, the group evaluates as true only if all its conditions
        would normally evaluate as false.
      </Content>
    }
  />
)

type OperatorSelectProps = {
  groupId: string
  index: number
  operator: LogicalOperator
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
  isDisabled: boolean
}

function OperatorSelect({ groupId, index, operator, onSelect, isDisabled }: OperatorSelectProps) {
  const [isOpen, setIsOpen] = useState(false)

  const toggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isDisabled={isDisabled}
        isFullWidth
        aria-label="Logical operator"
        id={`rule-${groupId}-${index}`}
      >
        {operator}
      </MenuToggle>
    ),
    [isOpen, isDisabled, groupId, index, operator]
  )

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      onSelect(_event, value)
      setIsOpen(false)
    },
    [onSelect]
  )

  const select = (
    <SynSelect isOpen={isOpen} onSelect={handleSelect} onOpenChange={setIsOpen} toggle={toggle} selected={operator}>
      <SelectList aria-label="Logical operator">
        <SelectOption value="AND">AND</SelectOption>
        <SelectOption value="OR">OR</SelectOption>
      </SelectList>
    </SynSelect>
  )

  if (isDisabled) {
    return (
      <Tooltip content="All conditions in this group must follow the same rule. To switch between AND/OR, please adjust the first rule input at the top of this level.">
        {select}
      </Tooltip>
    )
  }

  return select
}

type ExpressionGroupProps = {
  /** The group data */
  group: ExpressionGroupType
  /** Callback when group is updated */
  onChange: (updates: Partial<ExpressionGroupType>) => void
  /** Callback when a child node is updated */
  onUpdateChild: (index: number, node: ExpressionNode) => void
  /** Callback when a child node should be removed */
  onRemoveChild: (index: number) => void
  /** Callback when a condition should be added */
  onAddCondition: () => void
  /** Callback when a group should be added */
  onAddGroup: () => void
  /** Callback when group should be removed */
  onRemove?: () => void
  /** Nesting level (for styling) */
  level?: number
  /** Whether to show error state */
  error?: boolean
}

/**
 * Expression group component
 *
 * Renders:
 * - Group header with operator selector and add/remove buttons
 * - Children (conditions and nested groups)
 * - Add condition/group buttons
 */
export function ExpressionGroup(props: ExpressionGroupProps) {
  const {
    group,
    onChange,
    onUpdateChild,
    onRemoveChild,
    onAddCondition,
    onAddGroup,
    onRemove,
    level = 0,
    error,
  } = props

  const handleOperatorSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      onChange({ operator: String(value) as LogicalOperator })
    },
    [onChange]
  )

  // Styling for visual hierarchy — level 0 has no border/padding so content fills the
  // full width of the parent (matching the mode dropdown above). Nested groups get
  // indented with a left accent border.
  const containerStyle: React.CSSProperties =
    level === 0
      ? { backgroundColor: 'var(--pf-t--global--color--surface--primary)' }
      : {
          border: '1px solid var(--pf-t--global--color--border--default)',
          borderRadius: 'var(--pf-t--global--border-radius--default)',
          padding: 'var(--pf-t--global--spacer--sm)',
          marginLeft: 'var(--pf-t--global--spacer--sm)',
          borderLeft: '2px solid var(--pf-t--global--color--brand--default)',
          backgroundColor: 'transparent',
        }

  return (
    <div style={containerStyle}>
      <Stack hasGutter>
        {/* NOT checkbox and Group label - only show for nested groups (level > 0) */}
        {level > 0 && (
          <>
            {/* NOT checkbox for group negation */}
            <StackItem>
              <Flex spaceItems={{ default: 'spaceItemsXs' }} alignItems={{ default: 'alignItemsCenter' }}>
                <FlexItem>
                  <Checkbox
                    id={`not-${group.id}`}
                    label="Not"
                    isChecked={group.negate ?? false}
                    onChange={(_event, checked) => onChange({ negate: checked })}
                    aria-label="Negate group"
                  />
                </FlexItem>
                <FlexItem>
                  <GroupNotHelp />
                </FlexItem>
              </Flex>
            </StackItem>

            {/* Group header with label and remove button */}
            <StackItem>
              <Flex
                alignItems={{ default: 'alignItemsCenter' }}
                justifyContent={{ default: 'justifyContentSpaceBetween' }}
              >
                <FlexItem>
                  <Flex spaceItems={{ default: 'spaceItemsXs' }} alignItems={{ default: 'alignItemsCenter' }}>
                    <FlexItem>
                      <Content
                        component={ContentVariants.p}
                        style={{ fontWeight: 'var(--pf-t--global--font--weight--bold)', margin: 0 }}
                      >
                        Group
                      </Content>
                    </FlexItem>
                    <FlexItem>
                      <GroupHelp />
                    </FlexItem>
                  </Flex>
                </FlexItem>
                {onRemove && (
                  <FlexItem>
                    <Button
                      variant="plain"
                      isDanger
                      size="sm"
                      onClick={onRemove}
                      icon={<RhUiTrashIcon />}
                      aria-label="Remove group"
                    />
                  </FlexItem>
                )}
              </Flex>
            </StackItem>
          </>
        )}

        {/* Children with AND/OR selector between them */}
        {group.children.map((child, index) => (
          <React.Fragment key={child.id}>
            {/* Show AND/OR selector before each child except the first */}
            {index > 0 && (
              <StackItem>
                <FormGroup
                  label={level > 0 ? 'Group rule' : 'Rule'}
                  labelHelp={level > 0 ? <GroupRuleHelp /> : <RuleHelp />}
                  fieldId={`rule-${group.id}-${index}`}
                >
                  <div style={{ maxWidth: '100px' }}>
                    <OperatorSelect
                      groupId={group.id}
                      index={index}
                      operator={group.operator}
                      onSelect={handleOperatorSelect}
                      isDisabled={index > 1}
                    />
                  </div>
                </FormGroup>
              </StackItem>
            )}

            <StackItem>
              {child.type === 'condition' ? (
                <ExpressionCondition
                  condition={child}
                  onChange={(updates) => onUpdateChild(index, { ...child, ...updates })}
                  onRemove={group.children.length > 1 ? () => onRemoveChild(index) : undefined}
                  error={error}
                />
              ) : (
                <ExpressionGroup
                  group={child}
                  onChange={(updates) => onUpdateChild(index, { ...child, ...updates })}
                  onUpdateChild={(childIndex, node) => {
                    const updatedChildren = [...child.children]
                    updatedChildren[childIndex] = node
                    onUpdateChild(index, { ...child, children: updatedChildren })
                  }}
                  onRemoveChild={(childIndex) => {
                    const updatedChildren = child.children.filter((_, i) => i !== childIndex)
                    onUpdateChild(index, { ...child, children: updatedChildren })
                  }}
                  onAddCondition={() => {
                    const updatedChildren = [...child.children, createDefaultCondition()]
                    onUpdateChild(index, { ...child, children: updatedChildren })
                  }}
                  onAddGroup={() => {
                    const updatedChildren = [...child.children, createDefaultGroup()]
                    onUpdateChild(index, { ...child, children: updatedChildren })
                  }}
                  onRemove={group.children.length > 1 ? () => onRemoveChild(index) : undefined}
                  level={level + 1}
                  error={error}
                />
              )}
            </StackItem>
          </React.Fragment>
        ))}

        {/* Add buttons at bottom */}
        <StackItem>
          <Flex spaceItems={{ default: 'spaceItemsSm' }}>
            <FlexItem>
              <Tooltip content="Adds a single row for a new field/operator/value comparison within the current group.">
                <Button variant="secondary" size="sm" onClick={onAddCondition} icon={<RhUiAddIcon />}>
                  Add condition
                </Button>
              </Tooltip>
            </FlexItem>
            <FlexItem>
              <Tooltip content='Creates a new nested logic container, allowing you to build multi-layered "And/Or" requirements.'>
                <Button variant="secondary" size="sm" onClick={onAddGroup} icon={<RhUiAddIcon />}>
                  Add group
                </Button>
              </Tooltip>
            </FlexItem>
          </Flex>
        </StackItem>
      </Stack>
    </div>
  )
}
