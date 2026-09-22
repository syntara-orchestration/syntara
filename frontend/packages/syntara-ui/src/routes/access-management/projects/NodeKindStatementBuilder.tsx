import {
  Alert,
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  FormGroup,
  MenuToggle,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  type MenuToggleElement,
} from '@patternfly/react-core'
import { useMemo, useState, type Ref } from 'react'

import { SynSelect } from '../../../components/SynSelect'
import { useNodeKindsQuery } from '../../../hooks/useNodeKindsQuery'

import {
  appendNodeKindStatement,
  buildNodeKindStatement,
  selectableNodeKinds,
  type NodeKindStatementAction,
  type NodeKindStatementEffect,
} from './nodeKindStatement'

const EFFECT_OPTIONS: { value: NodeKindStatementEffect; label: string }[] = [
  { value: 'allow', label: 'Allow' },
  { value: 'deny', label: 'Deny' },
]

const ACTION_OPTIONS: { value: NodeKindStatementAction; label: string }[] = [
  { value: 'write', label: 'Write (add to a workflow)' },
  { value: 'execute', label: 'Execute (run in a workflow)' },
  { value: 'both', label: 'Write and execute' },
]

type BuilderMenuToggleProps = {
  toggleRef: Ref<MenuToggleElement>
  id: string
  isOpen: boolean
  label: string
  onToggle: () => void
  isDisabled?: boolean
}

function BuilderMenuToggle({ toggleRef, id, isOpen, label, onToggle, isDisabled }: Readonly<BuilderMenuToggleProps>) {
  return (
    <MenuToggle id={id} ref={toggleRef} isExpanded={isOpen} onClick={onToggle} isDisabled={isDisabled} isFullWidth>
      {label}
    </MenuToggle>
  )
}

type NodeKindStatementBuilderProps = {
  /** Current contents of the statements JSON editor. */
  readonly statementsJson: string
  /** Receives the JSON text with the new statement appended. */
  readonly onAppend: (statementsJson: string) => void
}

/**
 * Compose a `workflow_node` policy statement without hand-writing JSON.
 *
 * The raw JSON editor stays the source of truth: this only appends a well-formed
 * statement to it. A deny is offered only for kinds the backend allows it for,
 * mirroring the 422 it would otherwise return.
 */
export function NodeKindStatementBuilder({ statementsJson, onAppend }: NodeKindStatementBuilderProps) {
  const { nodeKinds } = useNodeKindsQuery()
  const [effect, setEffect] = useState<NodeKindStatementEffect>('deny')
  const [action, setAction] = useState<NodeKindStatementAction>('write')
  const [kind, setKind] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [openMenu, setOpenMenu] = useState<'effect' | 'action' | 'kind' | null>(null)

  const availableKinds = useMemo(() => selectableNodeKinds(nodeKinds, effect, action), [nodeKinds, effect, action])
  const selectedKind = availableKinds.some((entry) => entry.kind === kind) ? kind : ''

  const toggleMenu = (menu: 'effect' | 'action' | 'kind') => setOpenMenu((current) => (current === menu ? null : menu))

  const handleAdd = () => {
    if (!selectedKind) return
    const result = appendNodeKindStatement(
      statementsJson,
      buildNodeKindStatement({ effect, action, kind: selectedKind })
    )
    if (result.json === undefined) {
      setError(result.error)
      return
    }
    setError(null)
    onAppend(result.json)
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component={ContentVariants.small}>
          Add a node-kind statement to the JSON below. Node kinds are targeted through the <code>kind</code> resource
          label; a deny is only available for kinds that may be denied.
        </Content>
      </StackItem>
      <StackItem>
        <Flex alignItems={{ default: 'alignItemsFlexEnd' }} gap={{ default: 'gapSm' }}>
          <FlexItem flex={{ default: 'flex_1' }}>
            <FormGroup label="Effect" fieldId="node-kind-statement-effect">
              <SynSelect
                id="node-kind-statement-effect"
                isOpen={openMenu === 'effect'}
                selected={effect}
                onOpenChange={(isOpen) => setOpenMenu(isOpen ? 'effect' : null)}
                onSelect={(_event, value) => {
                  setEffect(value as NodeKindStatementEffect)
                  setOpenMenu(null)
                }}
                toggle={(toggleRef) => (
                  <BuilderMenuToggle
                    toggleRef={toggleRef}
                    id="node-kind-statement-effect-toggle"
                    isOpen={openMenu === 'effect'}
                    label={EFFECT_OPTIONS.find((option) => option.value === effect)?.label ?? 'Select an effect'}
                    onToggle={() => toggleMenu('effect')}
                  />
                )}
              >
                <SelectList>
                  {EFFECT_OPTIONS.map((option) => (
                    <SelectOption key={option.value} value={option.value} isSelected={option.value === effect}>
                      {option.label}
                    </SelectOption>
                  ))}
                </SelectList>
              </SynSelect>
            </FormGroup>
          </FlexItem>
          <FlexItem flex={{ default: 'flex_1' }}>
            <FormGroup label="Action" fieldId="node-kind-statement-action">
              <SynSelect
                id="node-kind-statement-action"
                isOpen={openMenu === 'action'}
                selected={action}
                onOpenChange={(isOpen) => setOpenMenu(isOpen ? 'action' : null)}
                onSelect={(_event, value) => {
                  setAction(value as NodeKindStatementAction)
                  setOpenMenu(null)
                }}
                toggle={(toggleRef) => (
                  <BuilderMenuToggle
                    toggleRef={toggleRef}
                    id="node-kind-statement-action-toggle"
                    isOpen={openMenu === 'action'}
                    label={ACTION_OPTIONS.find((option) => option.value === action)?.label ?? 'Select an action'}
                    onToggle={() => toggleMenu('action')}
                  />
                )}
              >
                <SelectList>
                  {ACTION_OPTIONS.map((option) => (
                    <SelectOption key={option.value} value={option.value} isSelected={option.value === action}>
                      {option.label}
                    </SelectOption>
                  ))}
                </SelectList>
              </SynSelect>
            </FormGroup>
          </FlexItem>
          <FlexItem flex={{ default: 'flex_1' }}>
            <FormGroup label="Node kind" fieldId="node-kind-statement-kind">
              <SynSelect
                id="node-kind-statement-kind"
                isOpen={openMenu === 'kind'}
                selected={selectedKind || undefined}
                onOpenChange={(isOpen) => setOpenMenu(isOpen ? 'kind' : null)}
                onSelect={(_event, value) => {
                  setKind(String(value))
                  setOpenMenu(null)
                }}
                toggle={(toggleRef) => (
                  <BuilderMenuToggle
                    toggleRef={toggleRef}
                    id="node-kind-statement-kind-toggle"
                    isOpen={openMenu === 'kind'}
                    label={selectedKind || 'Select a node kind'}
                    onToggle={() => toggleMenu('kind')}
                    isDisabled={availableKinds.length === 0}
                  />
                )}
              >
                <SelectList>
                  {availableKinds.map((entry) => (
                    <SelectOption key={entry.kind} value={entry.kind} isSelected={entry.kind === selectedKind}>
                      {entry.kind}
                    </SelectOption>
                  ))}
                </SelectList>
              </SynSelect>
            </FormGroup>
          </FlexItem>
          <FlexItem>
            <Button variant="secondary" onClick={handleAdd} isAriaDisabled={!selectedKind}>
              Add node-kind statement
            </Button>
          </FlexItem>
        </Flex>
      </StackItem>
      {error && (
        <StackItem>
          <Alert variant="danger" isInline title={error} />
        </StackItem>
      )}
    </Stack>
  )
}
