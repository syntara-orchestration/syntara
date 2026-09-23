import { Alert, Content, ContentVariants, List, ListItem } from '@patternfly/react-core'

import { SynLabel } from '../../components/labels/SynLabel'
import { describeNodeLabels } from '../../utils/nodeLabels'

import { parseDeniedNodes } from './deniedNodes'
import styles from './DeniedNodesAlert.module.css'

export type DeniedNodesAlertProps = Readonly<{
  /** Raw `execution.denied_nodes` value from the API. */
  deniedNodes: unknown
  /** Node id → display name, resolved from the workflow definition when available. */
  nameMap?: Map<string, string>
}>

/**
 * Summary of the nodes a run was not allowed to execute.
 * Renders nothing when the execution has no denied nodes.
 */
export function DeniedNodesAlert({ deniedNodes, nameMap }: DeniedNodesAlertProps) {
  const entries = parseDeniedNodes(deniedNodes)
  if (entries.length === 0) return null

  return (
    <Alert variant="warning" isInline title="Denied nodes" data-testid="denied-nodes-alert">
      <Content component={ContentVariants.p}>
        These steps were skipped because a policy did not allow them to run for this execution.
      </Content>
      <List isPlain aria-label="Denied nodes">
        {entries.map((entry) => (
          <ListItem key={entry.nodeId} className={styles.deniedNodeEntry}>
            <strong>{nameMap?.get(entry.nodeId) ?? entry.nodeId}</strong>
            {entry.kind ? (
              <SynLabel className={styles.kindLabel}>{describeNodeLabels(entry.kind, entry.labels)}</SynLabel>
            ) : null}
            <Content component={ContentVariants.small}>
              {entry.deniedBy ? `Denied by policy "${entry.deniedBy}"` : 'Denied by policy'}
            </Content>
          </ListItem>
        ))}
      </List>
    </Alert>
  )
}
