import { Alert, Badge, Content } from '@patternfly/react-core'

type WorkflowReferencedParentsAlertProps = Readonly<{
  /** Total distinct published parents affected (unfiltered by visibility). */
  totalCount: number
  isError: boolean
  /** Lead line describing the impact (differs for publish vs delete). */
  title: string
  /** Optional explanatory line rendered under the title, before the impact count. */
  consequence?: string
  /** Noun for the affected-resources row. */
  resourceLabel?: string
  variant?: 'warning' | 'info'
}>

/**
 * Shared "used by published workflows" impact alert for the publish and delete dialogs.
 *
 * Count-only by design: the affected total is shown as a badge rather than a parent-name list,
 * which keeps the dialog usable when many parents are affected and avoids disclosing names a
 * caller may not be allowed to see. The full, RBAC-filtered parent list lives in the Used-By
 * drill-down instead.
 */
export function WorkflowReferencedParentsAlert({
  totalCount,
  isError,
  title,
  consequence,
  resourceLabel = 'Workflows',
  variant = 'warning',
}: WorkflowReferencedParentsAlertProps) {
  if (isError) {
    return (
      <Alert variant="warning" isInline isPlain title="Unable to check which workflows use this workflow.">
        Proceeding may affect workflows that use it as a sub-workflow.
      </Alert>
    )
  }

  if (totalCount === 0) return null

  return (
    <Alert variant={variant} isInline title={title}>
      <Content>
        {consequence && <Content component="p">{consequence}</Content>}
        <Content component="p">
          {resourceLabel} <Badge isRead>{totalCount}</Badge>
        </Content>
      </Content>
    </Alert>
  )
}
