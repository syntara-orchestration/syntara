import { Tab, TabTitleText } from '@patternfly/react-core'

import { AppRoute } from '../../app/AppRoute'
import { breadcrumbsTasksTab } from '../../app/breadcrumbBuilders'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynListPanel, SynListPanelTabs } from '../../components/panels/list/SynListPanel'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useUrlTab } from '../../hooks/useUrlTab'
import { useDocLink } from '../../utils/docs/useDocLink'
import { ApprovalsListPanel } from '../approvals/ApprovalsListPanel'

import { FormResponsesListPanel } from './formResponses/FormResponsesListPanel'
import { TASKS_TAB_APPROVALS, TASKS_TAB_FORM_RESPONSES, useTasksTabAccess } from './useTasksTabAccess'

const TASKS_BASE_PATH = AppRoute.Tasks.Root

/** Tasks shell (tabs + list panels). Render inside {@link TasksAccessGate} from the route. */
export default function Tasks() {
  const { visibleTabs } = useTasksTabAccess()
  const { ProjectSelector } = useProjectSelector()
  const [activeTab] = useUrlTab(TASKS_BASE_PATH, visibleTabs[0] ?? TASKS_TAB_APPROVALS)
  const tabForBreadcrumb = activeTab === TASKS_TAB_FORM_RESPONSES ? TASKS_TAB_FORM_RESPONSES : TASKS_TAB_APPROVALS
  const breadcrumbs = breadcrumbsTasksTab(tabForBreadcrumb)
  const docKey = activeTab === TASKS_TAB_FORM_RESPONSES ? 'formResponses' : 'tasks'
  const tasksDocLink = useDocLink(docKey)

  return (
    <SynPage>
      <SynPageTitle segments={['Tasks']} />
      <SynPageHeader
        title="Tasks"
        docLink={tasksDocLink ?? undefined}
        projectSelector={ProjectSelector}
        breadcrumbs={breadcrumbs}
      />
      <SynPageBody>
        <SynListPanel>
          <SynListPanelTabs
            basePath={TASKS_BASE_PATH}
            defaultTab={visibleTabs[0] ?? TASKS_TAB_APPROVALS}
            validTabs={visibleTabs}
            aria-label="Tasks"
          >
            {visibleTabs.includes(TASKS_TAB_APPROVALS) && (
              <Tab eventKey={TASKS_TAB_APPROVALS} title={<TabTitleText>Approvals</TabTitleText>} />
            )}
            {visibleTabs.includes(TASKS_TAB_FORM_RESPONSES) && (
              <Tab eventKey={TASKS_TAB_FORM_RESPONSES} title={<TabTitleText>Form responses</TabTitleText>} />
            )}
          </SynListPanelTabs>

          {activeTab === TASKS_TAB_APPROVALS && visibleTabs.includes(TASKS_TAB_APPROVALS) ? (
            <ApprovalsListPanel embedded tabKey={TASKS_TAB_APPROVALS} tabLabel="Approvals" />
          ) : null}
          {activeTab === TASKS_TAB_FORM_RESPONSES && visibleTabs.includes(TASKS_TAB_FORM_RESPONSES) ? (
            <FormResponsesListPanel tabKey={TASKS_TAB_FORM_RESPONSES} tabLabel="Form responses" />
          ) : null}
        </SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}
