import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { SynLoadingState } from '../../../components/states/SynLoadingState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { detachPromise } from '../../../utils/detachPromise'

type ExecutionDetailErrorStatesProps = Readonly<{
  executionId: string | undefined
  isLoading: boolean
  error: unknown
  onRetry: () => Promise<unknown>
}>

/**
 * Renders error and loading states for ExecutionDetail page.
 * Returns null if execution data is available (no error, not loading).
 */
export function ExecutionDetailErrorStates({
  executionId,
  isLoading,
  error,
  onRetry,
}: ExecutionDetailErrorStatesProps) {
  if (!executionId) {
    return (
      <SynPage>
        <SynPageTitle segments={['Workflow Runs']} />
        <SynPageHeader title="Error" />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynErrorState title="Invalid execution" message="No execution ID provided" />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (error) {
    return (
      <SynPage>
        <SynPageTitle segments={['Workflow Runs']} />
        <SynPageHeader title="Error loading execution" />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynErrorState title="Error loading execution" message={error} onRetry={() => detachPromise(onRetry())} />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (isLoading) {
    return (
      <SynPage>
        <SynPageTitle segments={['Workflow Runs']} />
        <SynPageHeader title="Loading execution" />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynLoadingState />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return null
}
