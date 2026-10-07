import { rootRoute } from './routes/__root'
import { accessManagementRoutes } from './routes/access-management'
import { approvalsRoutes } from './routes/approvals'
import { authenticationRoutes } from './routes/authentication'
import { builderRoutes } from './routes/builder'
import { configurationRoutes } from './routes/configuration'
import { executionsRoutes } from './routes/executions'
import { myProfileRoutes } from './routes/my-profile'
import { settingsRoutes } from './routes/settings'
import { supportRoutes } from './routes/support'
import { tasksRoutes } from './routes/tasks'
import { workflowsRoutes } from './routes/workflows'

export const buildTanStackRouteTree = () =>
  rootRoute.addChildren([
    ...builderRoutes,
    ...workflowsRoutes,
    ...executionsRoutes,
    ...tasksRoutes,
    ...approvalsRoutes,
    ...configurationRoutes,
    ...settingsRoutes,
    ...authenticationRoutes,
    ...accessManagementRoutes,
    ...myProfileRoutes,
    ...supportRoutes,
  ])
