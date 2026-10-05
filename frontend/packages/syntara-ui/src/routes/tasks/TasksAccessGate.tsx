import { useQueryClient } from '@tanstack/react-query'
import { Spinner } from '@patternfly/react-core'

import { AppRoute } from '../../app/AppRoute'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynEmptyStateAccessDenied } from '../../components/states/SynEmptyStateAccessDenied'
import { SynErrorState } from '../../components/states/SynErrorState'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useUrlTab } from '../../hooks/useUrlTab'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import Tasks from './Tasks'
import { TASKS_TAB_FORM_RESPONSES, useTasksTabAccess } from './useTasksTabAccess'

const TASKS_BASE_PATH = AppRoute.Tasks.Root

/**
 * Route entry for `/tasks/:tab`. Centralizes permission loading, errors, and access
 * denied before rendering the Tasks shell (same OR gate as nav: approval or form_prompt read).
 */
export default function TasksAccessGate() {
  const queryClient = useQueryClient()
  const { visibleTabs, isChecking, canViewTasks, isError } = useTasksTabAccess()
  const [activeTab] = useUrlTab(TASKS_BASE_PATH, visibleTabs[0] ?? 'approvals')
  const docKey = activeTab === TASKS_TAB_FORM_RESPONSES ? 'formResponses' : 'tasks'
  const tasksDocLink = useDocLink(docKey)

  const retryPermissionChecks = () => {
    detachPromise(queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] }))
    detachPromise(queryClient.invalidateQueries({ queryKey: ['all-permissions'] }))
  }

  if (isChecking) {
    return (
      <SynPage>
        <SynPageTitle segments={['Tasks']} />
        <SynPageHeader title="Tasks" docLink={tasksDocLink ?? undefined} />
        <SynPageBody isCentered>
          <Spinner aria-label="Loading task permissions" />
        </SynPageBody>
      </SynPage>
    )
  }

  if (isError) {
    return (
      <SynPage>
        <SynPageTitle segments={['Tasks']} />
        <SynPageHeader title="Tasks" docLink={tasksDocLink ?? undefined} />
        <SynPageBody isCentered>
          <SynErrorState
            title="Unable to verify permissions"
            message={{
              title: 'Unable to verify permissions',
              detail: 'The permission check failed. Please try again.',
              retryable: true,
            }}
            onRetry={retryPermissionChecks}
          />
        </SynPageBody>
      </SynPage>
    )
  }

  if (!canViewTasks) {
    return (
      <SynPage>
        <SynPageTitle segments={['Tasks']} />
        <SynPageHeader title="Tasks" docLink={tasksDocLink ?? undefined} />
        <SynPageBody isCentered>
          <SynEmptyStateAccessDenied description="You do not have permission to view tasks. Contact your administrator to request access." />
        </SynPageBody>
      </SynPage>
    )
  }

  return <Tasks />
}
