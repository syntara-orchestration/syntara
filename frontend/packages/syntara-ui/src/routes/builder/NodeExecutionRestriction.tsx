import { Icon } from '@patternfly/react-core'
import { RhUiLockIcon } from '@patternfly/react-icons'
import { createContext, use } from 'react'
import type { ReactNode } from 'react'

import { useCanI } from '../../hooks/useCanI'

import styles from './NodeExecutionRestriction.module.css'

const NodeExecutionPermissionContext = createContext<string | null>(null)

export function NodeExecutionPermissionProvider(props: Readonly<{ resourceProject?: string; children: ReactNode }>) {
  return (
    <NodeExecutionPermissionContext.Provider value={props.resourceProject ?? ''}>
      {props.children}
    </NodeExecutionPermissionContext.Provider>
  )
}

export function NodeExecutionRestriction(props: Readonly<{ kind?: string }>) {
  const resourceProject = use(NodeExecutionPermissionContext)
  if (resourceProject === null || !props.kind) return null

  return <NodeExecutionRestrictionQuery kind={props.kind} resourceProject={resourceProject} />
}

function NodeExecutionRestrictionQuery(props: Readonly<{ kind: string; resourceProject: string }>) {
  const { allowed, isChecking, isError } = useCanI('execute', 'workflow_node', {
    ...(props.resourceProject ? { resourceProject: props.resourceProject } : {}),
    resourceLabels: { kind: props.kind },
  })

  if (allowed || isChecking || isError) return null

  return (
    <div className={styles.executionRestricted} role="img" aria-label="Execution restricted">
      <Icon size="md">
        <RhUiLockIcon
          aria-hidden="true"
          data-testid="execution-restriction-icon"
          style={{ color: 'var(--pf-t--global--color--status--warning--default)' }}
        />
      </Icon>
    </div>
  )
}
