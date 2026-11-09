import { Truncate } from '@patternfly/react-core'

import * as routeRefs from '../../app/routes/routeReferences'
import { LinkCell } from '../../components/table/LinkCell'

type ExecutionRunIdCellProps = {
  executionId: string
}

/** Run ID column cell: linked, monospace execution identifier. */
export function ExecutionRunIdCell({ executionId }: Readonly<ExecutionRunIdCellProps>) {
  /* v8 ignore start -- phantom branches from React Compiler on trivial link cell JSX */
  return (
    <LinkCell options={{ to: routeRefs.executionDetailRoute.fullPath, params: { executionId } }}>
      <code>
        <Truncate content={executionId} />
      </code>
    </LinkCell>
  )
  /* v8 ignore stop */
}
